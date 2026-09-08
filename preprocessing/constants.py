import re

KSR_CODE_PATTERN = re.compile(r"\d+\.\d+\.\d+\.\d+-\d+")
KSR_ROW_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.\d+-\d+$")

# Column indices in source Excel (0-based), sheet "Лист1" / "МТР"
SOURCE_COLUMNS = {
    "ks_number": 0,
    "estimate_code": 1,
    "resource_type": 2,
    "justification_source": 4,
    "name_raw": 5,
    "unit_raw": 6,
    "consumption": 7,
    "base_price": 8,
    "total_cost": 9,
}

REQUIRED_SOURCE_FIELDS = ("name_raw", "unit_raw")
