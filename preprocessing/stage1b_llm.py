from __future__ import annotations

import json
import re
from typing import Any, Callable

from preprocessing.catalog import MaterialCatalog
from preprocessing.neuro_gateway import DEFAULT_MODEL, llama_chat


def normalize_unit(unit_raw: str) -> str:
    unit = (unit_raw or "").strip().rstrip(".")
    replacements = {
        "шт.": "шт",
        "кг.": "кг",
        "м3": "м³",
        "м2": "м²",
        "шт": "шт",
    }
    key = unit.lower()
    if key in replacements:
        return replacements[key]
    if key in {"шт", "шт."}:
        return "шт"
    return unit


def _parse_llm_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError(f"LLM response is not JSON: {text[:300]}")


def build_normalization_prompt(
    *,
    name_raw: str,
    ksr_name: str | None,
    characteristics: dict[str, Any],
    catalog_matches: list[str],
) -> str:
    chars_json = json.dumps(characteristics, ensure_ascii=False, indent=2)
    catalog_hint = "\n".join(f"- {m}" for m in catalog_matches[:5]) or "(нет совпадений)"
    ksr = ksr_name or "(нет)"

    return f"""Нормализуй позицию строительного ресурса (МТР).

Исходное наименование (name_raw):
{name_raw}

Наименование из справочника КСР (ksr_name) — ТОЛЬКО для смысла названия, НЕ для material:
{ksr}

Уже извлечённые regex-характеристики (не выдумывай и не меняй dn/pmax/tmax/и т.п.):
{chars_json}

Похожие наименования из каталога — ТОЛЬКО подсказка для name_normalized, НЕ для material:
{catalog_hint}

Задачи (по приоритету):
1. material — вещество / сплав / сырьё из name_raw (НЕ вид изделия).
   Что считать material: сталь, нержавеющая сталь, нж, углеродистая сталь, медь, алюминий, бетон, чугун, базальтовое волокно, этиловый спирт и т.п.
   Что НЕ material (ставь null, это уйдёт в material_type): кабель, фильтр, геотекстиль, арматура, трубопровод, шпонка, лента, трап, болт, «нетканый геотекстиль», «ФУМ» как название изделия.
   Разрешено ТОЛЬКО если вещество/аббревиатура явно есть в name_raw:
   - слова материала в тексте, ИЛИ
   - аббревиатура: «нж», «угл.ст.» / «угл.ст», «медн…» и т.п.
   Примеры OK: «из нержавеющей стали» → «нержавеющая сталь»; «материал - нж» → «нж»; «угл.ст.» → «углеродистая сталь»; «с медными жилами» → «медь»; «спирт этиловый» → «этиловый спирт».
   Примеры FORBIDDEN (material = null): «Кабель КВВГ…» → не «кабель» и не «медь» без слова «медн»; «Лента ФУМ» → null; «Геотекстиль нетканый» → null (не «нетканый геотекстиль» и не полипропилен из каталога); фильтр/шпонка без указания сплава → null.
   ЗАПРЕЩЕНО: material из каталога, ksr_name, «типового исполнения», марки изделия.
2. name_normalized — краткое название без хвоста характеристик (DN/pmax/«По типу…»).
   Сохраняй тип изделия в названии (напр. «Кабель контрольный КВВГнг-FRLS 19х1,5», не только марку).
   ksr_name и каталог — только эталон формулировки названия, не источник material.
3. material_type — вид/категория изделия («кабель», «фильтр механический», «геотекстиль», «арматура запорная», «трубопровод»).
   Сюда относится то, что нельзя класть в material. null если неясно.

Жёсткие правила:
- material ≠ material_type: вещество/сплав vs вид изделия.
- НЕ добавляй dn, pmax, tmax, рабочую среду, класс безопасности и прочие ТХ, если их нет в name_raw.
- Для простых позиций (болт, гайка, ветошь) не выдумывай параметры и material.
- Ответ строго JSON без markdown:
{{
  "material": string|null,
  "material_type": string|null,
  "name_normalized": string,
  "confidence": number,
  "notes": string|null
}}
"""


def normalize_one_item(
    row: dict[str, Any],
    catalog: MaterialCatalog,
    *,
    model: str = DEFAULT_MODEL,
    chat_fn: Callable[..., str] = llama_chat,
) -> dict[str, Any]:
    """Stage 1b: enrich 1a row with LLM fields + catalog_matches."""
    name_raw = row.get("name_raw") or ""
    ksr_name = row.get("ksr_name")
    characteristics = dict(row.get("characteristics") or {})

    catalog_matches = catalog.matches_for(name_raw, top_k=5)

    prompt = build_normalization_prompt(
        name_raw=name_raw,
        ksr_name=ksr_name,
        characteristics=characteristics,
        catalog_matches=catalog_matches,
    )
    raw_answer = chat_fn(prompt, model=model, temperature=0.2, max_new_tokens=512)
    llm = _parse_llm_json(raw_answer)

    # Merge: regex characteristics stay; LLM only fills material / material_type
    regex_material = characteristics.get("material")
    llm_material = llm.get("material")
    if llm_material in ("", "null"):
        llm_material = None
    if llm_material:
        characteristics["material"] = str(llm_material).strip()
    elif regex_material:
        characteristics["material"] = regex_material
    else:
        characteristics["material"] = None

    llm_material_type = llm.get("material_type")
    if llm_material_type in ("", "null", None):
        characteristics["material_type"] = None
    else:
        characteristics["material_type"] = str(llm_material_type).strip()

    name_normalized = llm.get("name_normalized") or name_raw
    name_normalized = str(name_normalized).strip()

    confidence = llm.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else 0.7
    except (TypeError, ValueError):
        confidence = 0.7

    notes = llm.get("notes")
    if notes in ("", "null"):
        notes = None

    result = dict(row)
    result["characteristics"] = characteristics
    result["name_normalized"] = name_normalized
    result["catalog_matches"] = catalog_matches
    result["unit_normalized"] = normalize_unit(row.get("unit_raw") or "")
    result["confidence"] = confidence
    result["normalization_method"] = "code+llm"
    result["catalog_used"] = bool(catalog_matches)
    result["notes"] = notes
    return result


def normalize_items_llm(
    rows: list[dict[str, Any]],
    catalog: MaterialCatalog,
    *,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    progress: bool = True,
    chat_fn: Callable[..., str] = llama_chat,
) -> list[dict[str, Any]]:
    subset = rows[:limit] if limit is not None else rows
    results: list[dict[str, Any]] = []
    total = len(subset)
    for idx, row in enumerate(subset, start=1):
        if progress:
            print(f"  [{idx}/{total}] {row.get('item_id')} ...", flush=True)
        try:
            results.append(
                normalize_one_item(row, catalog, model=model, chat_fn=chat_fn)
            )
        except Exception as exc:  # keep pipeline going on single-item failures
            failed = dict(row)
            chars = dict(failed.get("characteristics") or {})
            failed["characteristics"] = chars
            failed["name_normalized"] = failed.get("name_raw") or ""
            failed["catalog_matches"] = catalog.matches_for(
                failed.get("name_raw") or "", top_k=5
            )
            failed["unit_normalized"] = normalize_unit(failed.get("unit_raw") or "")
            failed["confidence"] = 0.0
            failed["normalization_method"] = "code"
            failed["catalog_used"] = bool(failed["catalog_matches"])
            failed["notes"] = f"LLM error: {exc}"
            results.append(failed)
            if progress:
                print(f"    ! error: {exc}", flush=True)
    return results
