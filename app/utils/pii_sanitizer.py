"""PII 识别与脱敏 —— 全项目唯一实现。

背景（2026-09-23 收敛）
----------------------
此前存在两份互不相干的实现：本模块（`sanitize` / `detect_pii_fields`）
与 `app/services/runtime_audit.py` 里的 `scan_sensitive`（各自维护一套正则），
**且两份都没有被任何请求路径调用** —— 也就是说白皮书宣称的「数据脱敏」
护栏当时只是摆设。现在：

- 本模块是唯一实现，`runtime_audit.scan_sensitive` 改为委托到这里；
- 新增 `sanitize_deep()` 供嵌套结构使用，并在审计落库前脱敏；
- 新增 `backend_info()` 暴露当前生效的识别后端，便于巡检时核对。

识别能力分两层
--------------
1. **确定性规则（默认可用，零依赖）**：中国大陆手机号、身份证（含 GB 11643
   校验位验证，显著降低误报）、银行卡（Luhn 校验）、护照、港澳台通行证、
   QQ、微信 ID、固话、邮箱、IP、车牌。
2. **可选 NER（Presidio）**：若环境里装了 `presidio-analyzer`，额外识别
   人名/地名/组织等非结构化实体，并保留其置信度。装不上就只用第 1 层 ——
   这也是当前生产环境的实际状态（ECS 仅 1.9GB 内存，未安装 Presidio）。
   **不要**把 Presidio 说成已启用；用 `backend_info()` 查真值。

诚实边界：规则层对「中文人名」无能为力（需要 NER），而 NER 对中文人名的
召回同样不完美。本模块定位是**降低泄露面**，不是保证零泄露。

两档严格度（`strict` 参数）
--------------------------
- `strict=True`（默认）：用校验位过滤，少误报 —— 用于脱敏、落库、分析统计。
- `strict=False`：只认形态，少漏报 —— 用于**隐私拦截**这类「漏报代价 >> 误报代价」
  的场景。`healthlens_agent/safety.py` 的输出 PII 红线走的就是这一档（它在
  无 FastAPI 的精简环境里运行，不能 import 本模块，故保留自己的形态级规则集，
  由 `tests/core/test_pii_parity.py` 守住「两侧识别的类型族一致」这条不变量）。
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# 确定性规则
# ---------------------------------------------------------------------------

_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)(\d{17}[\dXx]|\d{15})(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 银行卡：13-19 位连续数字（再用 Luhn 校验，避免把订单号当卡号）
_BANK_CARD = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
# 中国大陆护照：E + 8 位；因公护照 D/S/P + 7-8 位
_PASSPORT = re.compile(r"(?<![A-Za-z0-9])(?:[EDSP]\d{7,8})(?![A-Za-z0-9])")
# 港澳台通行证
_HK_MO_PERMIT = re.compile(r"(?<![A-Za-z0-9])[CW]\d{8}(?![A-Za-z0-9])")
_TW_PERMIT = re.compile(r"(?<![A-Za-z0-9])\d{8}(?![A-Za-z0-9])")
# QQ：5-11 位数字，前置显式标签（裸数字不识别，避免误伤）
_QQ = re.compile(r"(?i)(?:qq|扣扣)\s*[:：]?\s*(\d{5,11})")
# 微信：wxid_ 开头，或显式标签
_WECHAT = re.compile(r"(?i)(?:wxid_[a-z0-9_\-]{6,}|(?:微信|wechat|weixin)\s*(?:号|id)?\s*[:：]?\s*[A-Za-z][A-Za-z0-9_\-]{5,19})")
_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_CN_PLATE = re.compile(r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{4,5}[A-HJ-NP-Z0-9挂学警港澳]")

# 掩码标签
_LABELS = {
    "phone": "[PHONE]",
    "landline": "[PHONE]",
    "id_card": "[ID_CARD]",
    "email": "[EMAIL]",
    "bank_card": "[BANK_CARD]",
    "passport": "[PASSPORT]",
    "hk_mo_permit": "[PERMIT]",
    "tw_permit": "[PERMIT]",
    "qq": "[QQ]",
    "wechat": "[WECHAT]",
    "ipv4": "[IP]",
    "cn_plate": "[PLATE]",
    "person": "[PERSON]",
    "location": "[LOCATION]",
    "organization": "[ORG]",
    "pii": "[PII]",
}


# ---------------------------------------------------------------------------
# 校验位：用于降低规则层误报
# ---------------------------------------------------------------------------

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECKSUM = "10X98765432"


def _id_card_valid(value: str) -> bool:
    """GB 11643-1999 校验位验证。15 位老号段无校验位，仅做日期合理性检查。"""
    v = value.strip().upper()
    if len(v) == 15:
        return v[:6].isdigit() and v[6:12].isdigit()
    if len(v) != 18:
        return False
    if not v[:17].isdigit():
        return False
    total = sum(int(v[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECKSUM[total % 11] == v[17]


def _luhn_valid(value: str) -> bool:
    digits = [int(c) for c in value]
    parity = len(digits) % 2
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# 可选后端：Presidio
# ---------------------------------------------------------------------------

_PRESIDIO = None
_PRESIDIO_CHECKED = False

_PRESIDIO_LANG_BY_CHAR = None


def _get_presidio():
    """惰性加载 Presidio。未安装返回 None（绝不因缺依赖报错）。"""
    global _PRESIDIO, _PRESIDIO_CHECKED
    if _PRESIDIO_CHECKED:
        return _PRESIDIO
    _PRESIDIO_CHECKED = True
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore

        _PRESIDIO = AnalyzerEngine()
    except Exception:
        _PRESIDIO = None
    return _PRESIDIO


_PRESIDIO_ENTITIES = [
    "PERSON", "LOCATION", "ORGANIZATION",
    "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "IP_ADDRESS",
]
_PRESIDIO_TO_TYPE = {
    "PERSON": "person",
    "LOCATION": "location",
    "ORGANIZATION": "organization",
    "PHONE_NUMBER": "phone",
    "EMAIL_ADDRESS": "email",
    "CREDIT_CARD": "bank_card",
    "IP_ADDRESS": "ipv4",
}


def _presidio_find(text: str) -> list[tuple[int, int, str]]:
    engine = _get_presidio()
    if engine is None or not text:
        return []
    try:
        results = engine.analyze(text=text, entities=_PRESIDIO_ENTITIES, language="en")
    except Exception:
        return []
    out = []
    for r in results:
        t = _PRESIDIO_TO_TYPE.get(r.entity_type, "pii")
        out.append((r.start, r.end, t))
    return out


# ---------------------------------------------------------------------------
# 规则层扫描
# ---------------------------------------------------------------------------

_RULE_SCANNERS: tuple[tuple[str, re.Pattern, Any], ...] = (
    ("phone", _PHONE, None),
    ("landline", _LANDLINE, None),
    ("id_card", _ID_CARD, _id_card_valid),
    ("email", _EMAIL, None),
    ("bank_card", _BANK_CARD, _luhn_valid),
    ("passport", _PASSPORT, None),
    ("hk_mo_permit", _HK_MO_PERMIT, None),
    ("wechat", _WECHAT, None),
    ("qq", _QQ, None),
    ("ipv4", _IPV4, None),
    ("cn_plate", _CN_PLATE, None),
)


def _rule_find(text: str, strict: bool = True) -> list[tuple[int, int, str]]:
    """strict=True 时用校验位过滤（少误报）；False 时只认形态（少漏报）。

    两档的分工很重要，别混用：
      - strict=True  用于**脱敏/落库**：宁可漏掉个别畸形号码，也不要误伤订单号。
      - strict=False 用于**隐私拦截**：宁可多拦一次（成本只是一次 BLOCK），
        也不要放过一个真号码。
    """
    hits: list[tuple[int, int, str]] = []
    for name, pattern, validator in _RULE_SCANNERS:
        for m in pattern.finditer(text):
            if strict and validator is not None and not validator(m.group(0)):
                continue
            hits.append((m.start(), m.end(), name))
    return hits


def find_pii(text: str, use_presidio: bool = True, strict: bool = True) -> list[dict]:
    """返回文本中的 PII 命中（按位置去重合并）。

    Presidio 可用时叠加 NER 结果；不可用时只跑规则层。
    strict=False 见 `_rule_find` 的说明。
    """
    if not text:
        return []
    hits = _rule_find(text, strict=strict)
    if use_presidio:
        hits.extend(_presidio_find(text))
    # 按起点排序，去重叠（保留更长/更早的命中）
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, name in hits:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end, name))
    return [
        {"type": n, "start": s, "end": e, "text": text[s:e]}
        for s, e, n in merged
    ]


def detect_pii(text: str, strict: bool = True) -> list[str]:
    """返回命中的 PII 类型名（去重、稳定排序）。"""
    seen = []
    for h in find_pii(text, strict=strict):
        if h["type"] not in seen:
            seen.append(h["type"])
    return sorted(seen)


def sanitize(text: str, use_presidio: bool = True, strict: bool = True) -> str:
    """把文本中的 PII 替换为占位标签。输入非字符串时原样返回。"""
    if not isinstance(text, str) or not text:
        return text
    hits = find_pii(text, use_presidio=use_presidio, strict=strict)
    if not hits:
        return text
    out = []
    cursor = 0
    for h in hits:
        out.append(text[cursor:h["start"]])
        out.append(_LABELS.get(h["type"], "[PII]"))
        cursor = h["end"]
    out.append(text[cursor:])
    return "".join(out)


def sanitize_deep(obj: Any, use_presidio: bool = True) -> Any:
    """递归脱敏 dict / list / tuple / str。不修改入参，返回新对象。"""
    if isinstance(obj, str):
        return sanitize(obj, use_presidio=use_presidio)
    if isinstance(obj, dict):
        return {k: sanitize_deep(v, use_presidio) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(sanitize_deep(v, use_presidio) for v in obj)
    return obj


def contains_pii(text: str) -> bool:
    return bool(find_pii(text))


# ---------------------------------------------------------------------------
# 兼容旧接口
# ---------------------------------------------------------------------------

# 字段名启发式：结构化的 PII 字段检测（与文本扫描互补）
_PII_KEYWORDS = (
    "name", "phone", "email", "idcard", "id_card", "address",
    "mobile", "passport", "bankcard", "bank_card", "wechat", "qq",
    "realname", "real_name", "contact",
)


def detect_pii_fields(data: dict) -> list[str]:
    """检测 dict 中可能包含 PII 的字段名（按字段名启发式，不扫描值）。"""
    found = []
    for key in data or {}:
        norm = str(key).lower().replace("_", "").replace("-", "")
        for kw in _PII_KEYWORDS:
            if kw.replace("_", "") in norm:
                found.append(key)
                break
    return found


def backend_info() -> dict:
    """当前实际生效的识别后端 —— 用于对外材料与巡检核对，不要凭记忆声明。"""
    engine = _get_presidio()
    return {
        "rule_layer": True,
        "rule_types": sorted({n for n, _, _ in _RULE_SCANNERS}),
        "presidio_available": engine is not None,
        "presidio_entities": _PRESIDIO_ENTITIES if engine is not None else [],
        "note": (
            "规则层始终可用；presidio_available=False 表示当前环境未安装 "
            "presidio-analyzer，中文人名类实体不会被告警。"
        ),
    }
