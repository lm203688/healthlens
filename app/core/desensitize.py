"""
HealthLens 数据脱敏模块

三级脱敏：
- mask（掩码）：保留前后若干字符，中间替换为 *
- pseudonymize（假名化）：用确定性哈希替换，保持同一实体的稳定性
- anonymize（匿名化）：完全去除，替换为占位符

支持字段：姓名/身份证/手机号/地址/邮箱/病历号/银行卡
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

SALT = "healthlens_desensitize_2026"


def _hash_pseudonym(value: str, prefix: str = "HL") -> str:
    """确定性假名化：SHA256 + 前缀，同一输入总是同一输出。"""
    raw = f"{SALT}:{value}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"{prefix}_{h}"


# ---------------------------------------------------------------------------
# 各字段脱敏规则
# ---------------------------------------------------------------------------

_PATTERNS = {
    "id_card": re.compile(r"\b(\d{6})(\d{8})(\d{3})\d\b"),  # 18位
    "phone": re.compile(r"\b1[3-9]\d{9}\b"),
    "bank_card": re.compile(r"\b(?:\d{4}[-\s]?){12,16}\d\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}


def _mask(value: str, keep_head: int = 3, keep_tail: int = 3) -> str:
    if not value or len(value) <= keep_head + keep_tail:
        return "*" * len(value)
    return value[:keep_head] + "*" * (len(value) - keep_head - keep_tail) + value[-keep_tail:]


@dataclass
class DesensitizeConfig:
    """脱敏配置。"""
    level: str = "mask"  # mask / pseudonymize / anonymize
    fields: list[str] = None  # None = 全部

    def __post_init__(self):
        if self.fields is None:
            self.fields = [
                "name", "real_name", "id_card", "id_number",
                "phone", "mobile", "email", "address",
                "bank_card", "card", "patient_id", "record_id",
            ]


def desensitize_record(record: dict, config: DesensitizeConfig | None = None) -> dict:
    """
    对单条记录做脱敏。返回脱敏后的副本（原记录不变）。

    脱敏规则：
    - mask: name→张**, id_card→110***1990***1234, phone→138****5678
    - pseudonymize: name→HL_a1b2c3d4, id_card→HL_e5f6g7h8
    - anonymize: name→[已脱敏], id_card→[已脱敏]
    """
    if config is None:
        config = DesensitizeConfig()

    result = dict(record)
    for field_name in config.fields:
        value = result.get(field_name)
        if value is None:
            continue
        value_str = str(value)

        if config.level == "mask":
            if field_name in ("id_card",):
                m = _PATTERNS["id_card"].search(value_str)
                if m:
                    result[field_name] = m.group(1) + "***" + m.group(2) + "***" + m.group(3) + "*"
                else:
                    result[field_name] = _mask(value_str)
            elif field_name in ("phone", "mobile"):
                m = _PATTERNS["phone"].search(value_str)
                result[field_name] = m.group(0)[:3] + "****" + m.group(0)[-4:] if m else _mask(value_str)
            elif field_name in ("bank_card", "card"):
                result[field_name] = _mask(value_str.replace(" ", "").replace("-", ""), keep_head=4, keep_tail=4)
            elif field_name in ("email",):
                m = _PATTERNS["email"].search(value_str)
                if m:
                    local, domain = m.group(0).split("@")
                    result[field_name] = local[:2] + "****@" + domain
                else:
                    result[field_name] = _mask(value_str)
            elif field_name in ("name", "real_name"):
                result[field_name] = value_str[0] + "**" if len(value_str) > 1 else value_str[0]
            else:
                result[field_name] = _mask(value_str)

        elif config.level == "pseudonymize":
            result[field_name] = _hash_pseudonym(value_str, prefix=field_name[:4].upper())

        elif config.level == "anonymize":
            result[field_name] = "[已脱敏]"

    return result


def desensitize_batch(records: list[dict], config: DesensitizeConfig | None = None) -> list[dict]:
    """批量脱敏。"""
    return [desensitize_record(r, config) for r in records]


# ---------------------------------------------------------------------------
# 字段扫描：自动发现记录中的敏感字段
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS: dict[str, re.Pattern] = {
    "id_card": _PATTERNS["id_card"],
    "phone": _PATTERNS["phone"],
    "bank_card": _PATTERNS["bank_card"],
    "email": _PATTERNS["email"],
}


def scan_sensitive(record: dict) -> list[str]:
    """扫描单条记录，返回命中的敏感字段名列表。"""
    found = []
    for field, value in record.items():
        if not isinstance(value, str):
            continue
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(value):
                found.append(f"{field}({label})")
                break
        # 简单的姓名检测（中文字符 2-4 位）
        if re.match(r"^[\u4e00-\u9fff]{2,4}$", value) and field in ("name", "real_name", "patient_name"):
            if not any("name" in f for f in found):
                found.append(f"{field}(name)")
    return found


__all__ = [
    "DesensitizeConfig",
    "desensitize_record",
    "desensitize_batch",
    "scan_sensitive",
]