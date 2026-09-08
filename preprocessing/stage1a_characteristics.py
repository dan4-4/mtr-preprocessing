from __future__ import annotations

from typing import Any

from preprocessing.characteristics import extract_characteristics
from preprocessing.models import ResourceItem


def enrich_with_characteristics(items: list[ResourceItem]) -> list[dict[str, Any]]:
    """
    Stage 1a (CODE): ResourceItem → ResourceItem + characteristics.

    Adds `characteristics` extracted from name_raw by regex patterns.
    Does not set name_normalized / catalog / LLM fields.
    """
    results: list[dict[str, Any]] = []
    for item in items:
        characteristics = extract_characteristics(item.name_raw)
        row = item.to_dict()
        row["characteristics"] = characteristics.to_dict()
        results.append(row)
    return results


def characteristics_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Coverage counts per characteristics field."""
    fields = [
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
    ]
    counts = {f: 0 for f in fields}
    any_filled = 0
    for row in rows:
        chars = row.get("characteristics") or {}
        filled = False
        for f in fields:
            val = chars.get(f)
            if f == "standards":
                ok = bool(val)
            else:
                ok = val is not None and val != ""
            if ok:
                counts[f] += 1
                filled = True
        if filled:
            any_filled += 1
    counts["any_characteristic"] = any_filled
    counts["total"] = len(rows)
    return counts
