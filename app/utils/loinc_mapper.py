# 基础 LOINC 映射框架，后续填充完整映射数据
COMMON_LOINC_CODES: dict[str, dict] = {
    "2345-7": {"name": "Glucose", "unit": "mg/dL", "range_low": 70, "range_high": 100},
    "2085-9": {"name": "HDL Cholesterol", "unit": "mg/dL", "range_low": 40, "range_high": 60},
    "13457-7": {"name": "LDL Cholesterol", "unit": "mg/dL", "range_low": 0, "range_high": 130},
    "2093-3": {"name": "Total Cholesterol", "unit": "mg/dL", "range_low": 0, "range_high": 200},
    "2544-0": {"name": "Triglycerides", "unit": "mg/dL", "range_low": 0, "range_high": 150},
    "14804-9": {"name": "Creatinine", "unit": "umol/L", "range_low": 44, "range_high": 133},
    "2823-3": {"name": "Potassium", "unit": "mmol/L", "range_low": 3.5, "range_high": 5.5},
    "2951-2": {"name": "Sodium", "unit": "mmol/L", "range_low": 135, "range_high": 145},
    "33914-3": {"name": "Urea", "unit": "mmol/L", "range_low": 1.7, "range_high": 8.3},
}

def lookup_loinc(code: str) -> dict | None:
    return COMMON_LOINC_CODES.get(code)

def search_loinc(keyword: str) -> list[dict]:
    results = []
    keyword_lower = keyword.lower()
    for code, info in COMMON_LOINC_CODES.items():
        if keyword_lower in info["name"].lower():
            results.append({"code": code, **info})
    return results