#!/usr/bin/env python3
"""Run preprocessing pipeline: stage 0 + 1a (regex) + optional 1b (LLM)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from preprocessing.catalog import MaterialCatalog
from preprocessing.models import ResourceItem
from preprocessing.neuro_gateway import DEFAULT_MODEL
from preprocessing.stage0_parser import parse_excel_to_resource_items
from preprocessing.stage1a_characteristics import (
    characteristics_stats,
    enrich_with_characteristics,
)
from preprocessing.stage1b_llm import normalize_items_llm


def _default_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / filename


def _name(stem: str, suffix: str) -> str:
    """Build output filename: stem + optional suffix + .json.

    Examples:
      suffix=""      → resource_items.json
      suffix="_test" → resource_items_test.json
    """
    return f"{stem}{suffix}.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preprocessing pipeline (stage 0 + 1a + optional 1b LLM)"
    )
    # --- TEST defaults (60 rows). For FULL run see comments below / --suffix "" ---
    parser.add_argument(
        "--input",
        type=Path,
        default=_default_path("Тестовый.xlsx"),
        # FULL: default=_default_path("6_Пример отчета мониторинга цен.xlsx"),
        help="Source Excel file (stage 0)",
    )
    parser.add_argument(
        "--ksr",
        type=Path,
        default=_default_path("Выгрузка КСР.xlsx"),
        help="KSR reference Excel",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=_default_path("6_Пример отчета мониторинга цен.xlsx"),
        help="Material catalog Excel (P/V/AB) — always the monitoring report",
    )
    parser.add_argument(
        "--from-resource-items",
        type=Path,
        default=None,
        help="Skip stage 0; load ResourceItem JSON",
    )
    parser.add_argument(
        "--from-characteristics",
        type=Path,
        default=None,
        help="Skip stage 0+1a; load characteristics JSON for stage 1b",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_path("output"),
        help="Output directory for JSON files",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_test",
        # FULL: default="",
        help='Filename suffix before .json (default "_test" → *_test.json; full run: "")',
    )
    parser.add_argument(
        "--stage1b",
        action="store_true",
        help="Run LLM normalization (needs NEIROSHLYUZ_TOKEN / .env.local)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N items in stage 1b (smoke tests)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"LLM model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print pipeline statistics",
    )
    args = parser.parse_args()

    suffix = args.suffix or ""
    if suffix and not suffix.startswith("_"):
        suffix = f"_{suffix}"

    args.output_dir.mkdir(parents=True, exist_ok=True)

    resource_path = args.output_dir / _name("resource_items", suffix)
    chars_path = args.output_dir / _name("resource_items_characteristics", suffix)
    normalized_path = args.output_dir / _name("normalized_items", suffix)

    if args.from_characteristics:
        print(f"Loading stage 1a rows from {args.from_characteristics} ...")
        with args.from_characteristics.open(encoding="utf-8") as f:
            enriched = json.load(f)
        print(f"  → {len(enriched)} items loaded")
        resource_items = None
    else:
        if args.from_resource_items:
            print(f"Loading ResourceItems from {args.from_resource_items} ...")
            with args.from_resource_items.open(encoding="utf-8") as f:
                raw = json.load(f)
            resource_items = [ResourceItem.from_dict(row) for row in raw]
            print(f"  → {len(resource_items)} ResourceItem loaded")
        else:
            print(f"Stage 0: parsing {args.input} ...")
            resource_items = parse_excel_to_resource_items(args.input, args.ksr)
            with resource_path.open("w", encoding="utf-8") as f:
                json.dump(
                    [item.to_dict() for item in resource_items],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            print(f"  → {len(resource_items)} ResourceItem → {resource_path}")

        print("Stage 1a: extracting characteristics (regex) ...")
        enriched = enrich_with_characteristics(resource_items)
        with chars_path.open("w", encoding="utf-8") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
        print(f"  → {len(enriched)} items → {chars_path}")

    if args.stage1b:
        print(f"Stage 1b: LLM normalization ({args.model}) ...")
        catalog = MaterialCatalog(args.catalog)
        print(f"  catalog index: {len(catalog)} names")
        normalized = normalize_items_llm(
            enriched,
            catalog,
            model=args.model,
            limit=args.limit,
        )
        with normalized_path.open("w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        print(f"  → {len(normalized)} NormalizedItem → {normalized_path}")

    if args.stats:
        total = len(enriched)
        if resource_items is not None:
            with_ksr = sum(1 for i in resource_items if i.ksr_code)
            ksr_found = sum(1 for i in resource_items if i.ksr_name)
            print("\nStatistics (stage 0):")
            print(f"  Total items:         {total}")
            print(f"  KSR codes extracted: {with_ksr}/{total}")
            print(f"  KSR names found:     {ksr_found}/{with_ksr or 1}")

        cstats = characteristics_stats(enriched)
        print("\nStatistics (stage 1a — characteristics coverage):")
        print(
            f"  Any characteristic:  {cstats['any_characteristic']}/{total} "
            f"({100 * cstats['any_characteristic'] / total:.1f}%)"
        )
        for field in (
            "material",
            "grade",
            "dn",
            "peak_pressure",
            "max_temperature",
            "working_medium",
            "safety_class",
            "connection_type",
            "control_type",
            "dimensions",
            "standards",
        ):
            n = cstats[field]
            print(f"  {field:18} {n}/{total} ({100 * n / total:.1f}%)")

        if args.stage1b:
            material_llm = sum(
                1
                for r in normalized
                if (r.get("characteristics") or {}).get("material")
            )
            mtype = sum(
                1
                for r in normalized
                if (r.get("characteristics") or {}).get("material_type")
            )
            with_catalog = sum(1 for r in normalized if r.get("catalog_matches"))
            ok = sum(1 for r in normalized if r.get("normalization_method") == "code+llm")
            print("\nStatistics (stage 1b — LLM):")
            print(f"  Processed:           {len(normalized)}")
            print(f"  LLM ok (code+llm):   {ok}/{len(normalized)}")
            print(f"  material filled:     {material_llm}/{len(normalized)}")
            print(f"  material_type filled:{mtype}/{len(normalized)}")
            print(f"  catalog_matches:     {with_catalog}/{len(normalized)}")


if __name__ == "__main__":
    main()
