import re

PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
ID_CARD_PATTERN = re.compile(r"\d{17}[\dXx]")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

def sanitize(text: str) -> str:
    text = PHONE_PATTERN.sub("[PHONE]", text)
    text = ID_CARD_PATTERN.sub("[ID_CARD]", text)
    text = EMAIL_PATTERN.sub("[EMAIL]", text)
    return text

def detect_pii_fields(data: dict) -> list[str]:
    """检测 dict 中可能包含 PII 的字段名"""
    pii_keywords = ["name", "phone", "email", "id_card", "address", "idcard", "mobile"]
    found = []
    for key in data:
        lower_key = key.lower().replace("_", "").replace("-", "")
        for keyword in pii_keywords:
            if keyword in lower_key:
                found.append(key)
                break
    return found