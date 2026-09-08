from __future__ import annotations

import re

from preprocessing.models import Characteristics

# --- DN / Ду (nominal diameter) ---
# Prefer Latin DN; fallback to Cyrillic Ду (with optional >/<)
DN_LATIN_PATTERN = re.compile(r"DN\s*\d+", re.IGNORECASE)
DU_CYR_PATTERN = re.compile(r"Ду\s*[<>]?\s*\d+\s*(?:мм|mm)?", re.IGNORECASE)

# --- Pressure / temperature ---
PMAX_PATTERN = re.compile(
    r"pmax\s*=\s*([\d.]+\s*MPag?)", re.IGNORECASE
)
TMAX_PATTERN = re.compile(
    r"tmax\s*=\s*(\d+\s*°\s*[СC])", re.IGNORECASE
)

# --- Explicit labeled fields ---
WORKING_MEDIUM_PATTERN = re.compile(
    r"Раб\.?\s*среда\s*:\s*(.+?)(?:;|$)", re.IGNORECASE
)
CONNECTION_TYPE_PATTERN = re.compile(
    r"Тип присоединения\s*:\s*(.+?)(?:[;,.]|$)", re.IGNORECASE
)
CONTROL_TYPE_PATTERN = re.compile(
    r"Способ управления\s*:\s*(.+?)(?:;|$)", re.IGNORECASE
)
MATERIAL_PATTERN = re.compile(
    r"материал\s*[-–—:]\s*([^\s,;_]+)", re.IGNORECASE
)

# --- Safety class ---
# Forms: "Кл4Н", "Кл. 4Н", "4 класса безопасности", "4Н класса безопасности"
SAFETY_CLASS_COMPACT = re.compile(r"Кл\.?\s*([\d]+Н?)", re.IGNORECASE)
SAFETY_CLASS_PHRASE = re.compile(
    r"(\d+\s*Н?)\s*класс[а]?\s+безопасности", re.IGNORECASE
)

# --- Grade / mark / model (priority order applied in code) ---
GRADE_PO_TIPU = re.compile(r"По типу\s+([^\s;,)]+)", re.IGNORECASE)
# "класс A500С", "класс В45 (М600)" — capture class token + optional (М…)
GRADE_KLASS = re.compile(
    r"класс\s+([A-Za-zА-Яа-яЁё0-9][\w\-]*(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)
# "марка А", 'марка Sikaplan "WT 1200-20C"', 'марка "Sika Waterbar…"'
GRADE_MARKA = re.compile(
    r"марка\s*[:]?[\s\"]*([A-Za-zА-Яа-яЁё0-9][^,_;]{0,80}?)"
    r"(?=\"?\s*(?:[,_(]|$|\s*для|\s*на\s|_))",
    re.IGNORECASE,
)
# Product model like "T MQK-600" (Hilti mounts etc.)
GRADE_MODEL = re.compile(r"\b([A-Z]\s+[A-Z]{2,}\w*-\d+)\b")

# --- Dimensions ---
# Pipe OD×wall lists: "Дн 159х6, 133х6, 89х5"
DIM_DN_CYR_LIST = re.compile(
    r"Дн\s*[\d.]+(?:\s*[xх×]\s*[\d.]+)?(?:\s*,\s*[\d.]+(?:\s*[xх×]\s*[\d.]+)?)*",
    re.IGNORECASE,
)
# "диаметр 25 мм", "Диаметр 32 мм"
DIM_DIAMETER = re.compile(
    r"[Дд]иаметр\s*[=:]?\s*\d+(?:[.,]\d+)?\s*(?:мм|mm)?",
    re.IGNORECASE,
)
# "толщ=50 mm", ширина/длина/размер
DIM_GENERIC = re.compile(
    r"(?:толщ(?:ина)?|ширина|длина|размер)\s*[=:]?\s*[\d.,\sxх×]+(?:\s*mm|мм)?",
    re.IGNORECASE,
)

# --- Standards (digit required after prefix) ---
STANDARDS_PATTERN = re.compile(
    r"(?:ГОСТ(?:\s*Р)?|ТУ|EN|ASTM|ISO|DIN(?:\s*EN)?)\s*[\d][\w\-\./]*",
    re.IGNORECASE,
)


def _first(*matches: re.Match | None) -> str | None:
    for m in matches:
        if m:
            return m.group(0).strip()
    return None


def _group1(*matches: re.Match | None) -> str | None:
    for m in matches:
        if m:
            return m.group(1).strip().strip('"').strip()
    return None


def _extract_dn(text: str) -> str | None:
    latin = DN_LATIN_PATTERN.search(text)
    if latin:
        return latin.group(0).strip()
    cyr = DU_CYR_PATTERN.search(text)
    if cyr:
        return re.sub(r"\s+", " ", cyr.group(0).strip())
    return None


def _extract_safety_class(text: str) -> str | None:
    phrase = SAFETY_CLASS_PHRASE.search(text)
    if phrase:
        return re.sub(r"\s+", "", phrase.group(1).strip().upper().replace("Н", "Н"))
    # normalize "4 Н" / "4Н" → keep digits+optional Н
    compact = SAFETY_CLASS_COMPACT.search(text)
    if compact:
        return compact.group(1).strip()
    return None


def _extract_grade(text: str) -> str | None:
    po_tipu = GRADE_PO_TIPU.search(text)
    if po_tipu:
        return po_tipu.group(1).strip().rstrip(")")
    klass = GRADE_KLASS.search(text)
    if klass:
        # skip "класса безопасности" — handled by safety_class
        val = klass.group(1).strip()
        if re.match(r"безопасности", val, re.IGNORECASE):
            pass
        else:
            return re.sub(r"\s+", " ", val)
    marka = GRADE_MARKA.search(text)
    if marka:
        return re.sub(r"\s+", " ", marka.group(1).strip().strip('"').strip())
    model = GRADE_MODEL.search(text)
    if model:
        return model.group(1).strip()
    return None


def _extract_dimensions(text: str) -> str | None:
    parts: list[str] = []
    for pattern in (DIM_DN_CYR_LIST, DIM_DIAMETER, DIM_GENERIC):
        m = pattern.search(text)
        if m:
            parts.append(re.sub(r"\s+", " ", m.group(0).strip()))
    if not parts:
        return None
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return "; ".join(uniq)


def extract_characteristics(name_raw: str) -> Characteristics:
    """Extract structured characteristics from name_raw via regex only.

    Fields are filled only when the value is explicitly present in the text.
    material_type stays null (semantic category — for LLM later).
    """
    text = name_raw or ""

    standards = list({m.group(0).strip() for m in STANDARDS_PATTERN.finditer(text)})

    pmax_match = PMAX_PATTERN.search(text)
    tmax_match = TMAX_PATTERN.search(text)
    medium_match = WORKING_MEDIUM_PATTERN.search(text)
    connection_match = CONNECTION_TYPE_PATTERN.search(text)
    control_match = CONTROL_TYPE_PATTERN.search(text)
    material_match = MATERIAL_PATTERN.search(text)

    # Avoid "класс безопасности" being captured as grade by GRADE_KLASS:
    # GRADE_KLASS uses "класс\s+X" — "класс безопасности" would match "безопасности"
    grade = _extract_grade(text)
    if grade and re.fullmatch(r"безопасности", grade, re.IGNORECASE):
        grade = None

    return Characteristics(
        material_type=None,
        material=_group1(material_match),
        grade=grade,
        dn=_extract_dn(text),
        peak_pressure=pmax_match.group(1).strip() if pmax_match else None,
        max_temperature=(
            re.sub(r"\s+", "", tmax_match.group(1).strip())
            if tmax_match
            else None
        ),
        working_medium=medium_match.group(1).strip() if medium_match else None,
        safety_class=_extract_safety_class(text),
        connection_type=(
            connection_match.group(1).strip() if connection_match else None
        ),
        control_type=control_match.group(1).strip() if control_match else None,
        dimensions=_extract_dimensions(text),
        standards=standards,
    )
