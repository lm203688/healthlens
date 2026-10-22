"""HealthLens 指标别名词典库。

从 `data/indicator_dictionary.yaml` 加载 16 项核心 lab/vitals 指标，
提供：
  - resolve_name():     中文名/英文名/别名 → canonical slug + LOINC
  - normalize_unit():   (value, unit_text) → canonical_value + unit_si
  - normalize_reference_range(): 分层参考区间取值 + in_range 判定
  - is_loinc_code():    判断字符串是否为已收录 LOINC

设计约束：
  - 无 numpy/pandas 依赖，仅 stdlib + PyYAML
  - 首次调用后 LRU 缓存，进程内只解析一次
  - YAML 缺失 / schema 违规 → 立即抛 IndicatorDictError（fail-loud，不 silent degrade）
  - 别名匹配 case-insensitive + 空白/下划线归一化 + 全半角归一
"""

from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# --- 常量 ---

_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "indicator_dictionary.yaml"

# 人口学分层枚举（严格闭合集合，新增需同步更新词典）
STRATA = ("adult_male", "adult_female", "pediatric", "senior")

# 别名匹配时用于归一化的字符替换表（全→半、非 ASCII 空格、下划线等）
_WHITESPACE_RE = re.compile(r"[\s\u3000_\-]+")
_PUNCT_RE = re.compile(r"[.,，。、;；:：/\\()（）\[\]{}（）【】]+")

_LEVEL_LOW = "low"
_LEVEL_NORMAL = "normal"
_LEVEL_HIGH = "high"


class IndicatorDictError(RuntimeError):
    """词典加载/查询失败（fail-loud）。"""


# --- 归一化工具 ---


def _normalize_alias(text: str) -> str:
    """别名匹配前的归一化：全半角、空白、标点、大小写。"""
    if not text:
        return ""
    # 全角 → 半角
    text = unicodedata.normalize("NFKC", text)
    # 空白/下划线/连字符 → 空
    text = _WHITESPACE_RE.sub("", text)
    # 移除标点
    text = _PUNCT_RE.sub("", text)
    return text.strip().lower()


def _normalize_unit(text: str) -> str:
    """单位归一化：仅做 NFKC + 空白/大小写处理，保留 / 和 ² 等特殊字符。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    # 单位内部大小写敏感（mmol/L 与 mmol/l 应等价），但外层键已按 YAML 定义
    return text


# --- 加载 ---


@lru_cache(maxsize=1)
def _load_dictionary() -> dict[str, Any]:
    """加载并校验 YAML 词典（进程内只解析一次）。"""
    if not _YAML_PATH.exists():
        raise IndicatorDictError(f"Indicator dictionary YAML not found: {_YAML_PATH}")

    try:
        with open(_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise IndicatorDictError(f"Failed to parse { _YAML_PATH }: {e}") from e

    if not isinstance(data, dict) or "indicators" not in data:
        raise IndicatorDictError("YAML missing top-level 'indicators' key")

    indicators = data["indicators"]
    if not isinstance(indicators, dict) or not indicators:
        raise IndicatorDictError("'indicators' must be a non-empty mapping")

    # schema 强校验（fail-loud）
    for slug, entry in indicators.items():
        _validate_entry(slug, entry)

    return data


def _validate_entry(slug: str, entry: Any) -> None:
    """单条指标 schema 校验。"""
    if not isinstance(entry, dict):
        raise IndicatorDictError(f"[{slug}] entry must be a mapping")

    required = ("loinc_code", "name_en", "name_cn", "unit_si", "unit_alt", "ref_range")
    missing = [k for k in required if k not in entry or entry[k] in (None, "")]
    if missing:
        raise IndicatorDictError(f"[{slug}] missing required keys: {missing}")

    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list) or not aliases:
        raise IndicatorDictError(f"[{slug}] aliases must be a non-empty list")

    unit_alt = entry["unit_alt"]
    if not isinstance(unit_alt, dict) or entry["unit_si"] not in unit_alt:
        raise IndicatorDictError(
            f"[{slug}] unit_alt must contain the SI unit '{entry['unit_si']}' as a key with factor 1.0"
        )
    for k, factor in unit_alt.items():
        if not isinstance(factor, (int, float)) or factor <= 0:
            raise IndicatorDictError(f"[{slug}] unit_alt['{k}'] must be positive number, got {factor!r}")

    ref_range = entry["ref_range"]
    if not isinstance(ref_range, dict):
        raise IndicatorDictError(f"[{slug}] ref_range must be a mapping")
    for stratum in STRATA:
        if stratum not in ref_range:
            raise IndicatorDictError(f"[{slug}] ref_range missing stratum '{stratum}'")
        rng = ref_range[stratum]
        if not isinstance(rng, dict) or "low" not in rng or "high" not in rng:
            raise IndicatorDictError(
                f"[{slug}] ref_range['{stratum}'] must have 'low' and 'high' numeric keys"
            )
        low, high = rng["low"], rng["high"]
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            raise IndicatorDictError(
                f"[{slug}] ref_range['{stratum}'] low/high must be numeric"
            )
        if low > high:
            raise IndicatorDictError(f"[{slug}] ref_range['{stratum}'] low({low}) > high({high})")


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """构建归一化别名 → canonical slug 索引。"""
    data = _load_dictionary()
    index: dict[str, str] = {}
    for slug, entry in data["indicators"].items():
        candidates = [entry["name_en"], entry["name_cn"], *entry["aliases"]]
        # slug 本身也是候选
        candidates.insert(0, slug)
        for c in candidates:
            key = _normalize_alias(str(c))
            if not key:
                continue
            if key in index and index[key] != slug:
                # 多 slug 命中同一归一化 key —— 视为歧义，保留首次，log warning
                logger.warning(
                    "indicator alias collision: '%s' → %s / %s (keeping first)",
                    key,
                    index[key],
                    slug,
                )
                continue
            index[key] = slug
    return index


@lru_cache(maxsize=1)
def _loinc_index() -> set[str]:
    """所有已收录 LOINC code（str 集合）。"""
    data = _load_dictionary()
    codes: set[str] = set()
    for entry in data["indicators"].values():
        code = entry.get("loinc_code")
        if isinstance(code, str):
            codes.add(code)
        elif isinstance(code, list):
            codes.update(str(c) for c in code)
    return codes


# --- 公开 API ---


def load_dictionary() -> dict[str, Any]:
    """返回整个词典字典（供 API catalog 端点使用）。"""
    return _load_dictionary()


def list_slugs() -> list[str]:
    """返回所有 canonical slug（按词典声明顺序）。"""
    return list(_load_dictionary()["indicators"].keys())


def get_entry(slug: str) -> dict[str, Any] | None:
    """按 canonical slug 获取完整条目。未知 slug 返回 None（不 raise）。"""
    return _load_dictionary()["indicators"].get(slug)


def resolve_name(name: str) -> dict[str, Any] | None:
    """把任意名称（中英/别名/大小写/标点变体）解析为 canonical entry。

    返回 dict：
      {
        "slug": "glucose",
        "name_en": "Fasting Glucose",
        "name_cn": "空腹血糖",
        "loinc_code": "2345-7",
        "unit_si": "mmol/L",
      }
    未命中返回 None。
    """
    if not name or not isinstance(name, str):
        return None
    key = _normalize_alias(name)
    if not key:
        return None
    slug = _alias_index().get(key)
    if not slug:
        return None
    entry = _load_dictionary()["indicators"][slug]
    return {
        "slug": slug,
        "name_en": entry["name_en"],
        "name_cn": entry["name_cn"],
        "loinc_code": entry["loinc_code"],
        "unit_si": entry["unit_si"],
    }


def normalize_unit(
    value: float | int | str,
    unit_text: str,
    slug: str | None = None,
) -> dict[str, Any]:
    """把 (value, unit_text) 换算到 unit_si。

    参数:
      value: 原始数值（str 也接受，做 float 转换）
      unit_text: 原始单位文本（如 "mg/dL", "mmol/L"）
      slug: 可选——指标 slug（如 "glucose" / "hdl"）。多指标共享同一 unit
        时（如 mg/dL 同时属于 glucose/TC/HDL/creat 等）**必须传 slug**，
        否则本函数无法判断用哪个指标的换算因子，返回 {"ok": False,
        "reason": "ambiguous_unit_without_slug"}。若传了 slug，只在该指标
        的 unit_alt 中查找；未传 slug 但 unit 只属于唯一指标时仍可换算。

    返回:
      {
        "slug": ...,
        "original_value": ...,
        "original_unit": ...,
        "canonical_value": ...,  # 换算到 unit_si 的数值
        "unit_si": ...,
        "factor": ...,
      }
      未识别 unit 返回 {"ok": False, "reason": "unknown_unit"}。
      多 slug 共享 unit 但未指定 slug 时返回 {"ok": False,
      "reason": "ambiguous_unit_without_slug", "candidates": [...]}。

    典型用法:
      先 `resolve_name("HbA1c")` → slug="hba1c"，
      再 `normalize_unit(6.2, "%", slug="hba1c")` → canonical_value=67.766
    """
    if unit_text is None:
        return {"ok": False, "reason": "missing_unit"}

    unit_key = _normalize_unit(str(unit_text))
    if not unit_key:
        return {"ok": False, "reason": "empty_unit"}

    # slug 指定模式：只在该 slug 内查
    data = _load_dictionary()
    if slug:
        entry = data["indicators"].get(slug)
        if entry is None:
            return {"ok": False, "reason": f"unknown_slug: {slug!r}"}
        return _convert_from_entry(slug, entry, value, unit_text, unit_key)

    # slug 未指定：先收集所有匹配的候选
    candidates: list[tuple[str, float, str]] = []
    for slug_candidate, entry in data["indicators"].items():
        hit = _match_factor(entry, unit_text, unit_key)
        if hit is not None:
            candidates.append((slug_candidate, hit[0], hit[1]))

    if not candidates:
        return {"ok": False, "reason": f"unknown_unit: {unit_text!r}"}
    if len(candidates) > 1:
        # 多 slug 共享该 unit —— 拒绝推断，要求调用方指定 slug
        return {
            "ok": False,
            "reason": "ambiguous_unit_without_slug",
            "candidates": [c[0] for c in candidates],
            "hint": "pass slug='...' to disambiguate (see resolve_name())",
        }
    # 唯一候选
    only_slug, factor, matched_key = candidates[0]
    try:
        raw = float(value)
    except (TypeError, ValueError) as e:
        return {"ok": False, "reason": f"invalid_value: {e}"}
    return {
        "ok": True,
        "slug": only_slug,
        "original_value": raw,
        "original_unit": matched_key,
        "canonical_value": raw * factor,
        "unit_si": data["indicators"][only_slug]["unit_si"],
        "factor": factor,
    }


def _match_factor(
    entry: dict[str, Any], unit_text: str, unit_key: str
) -> tuple[float, str] | None:
    """在单条 entry 的 unit_alt 中查找匹配 factor。返回 (factor, matched_key)。"""
    unit_alt = entry.get("unit_alt", {})
    for k, v in unit_alt.items():
        if k == unit_text:
            return v, k
    for k, v in unit_alt.items():
        if _normalize_unit(str(k)) == unit_key:
            return v, k
    return None


def _convert_from_entry(
    slug: str,
    entry: dict[str, Any],
    value: float | int | str,
    unit_text: str,
    unit_key: str,
) -> dict[str, Any]:
    """在指定 slug 的 entry 内做单位换算（不跨 slug 推断）。"""
    hit = _match_factor(entry, unit_text, unit_key)
    if hit is None:
        return {
            "ok": False,
            "reason": "unknown_unit",
            "slug": slug,
            "input_unit": unit_text,
            "supported_units": list(entry.get("unit_alt", {}).keys()),
        }
    factor, matched_key = hit
    try:
        raw = float(value)
    except (TypeError, ValueError) as e:
        return {"ok": False, "reason": f"invalid_value: {e}"}
    return {
        "ok": True,
        "slug": slug,
        "original_value": raw,
        "original_unit": matched_key,
        "canonical_value": raw * factor,
        "unit_si": entry["unit_si"],
        "factor": factor,
    }


def _normalize_unit_legacy_impl(value: float | int | str, unit_text: str) -> dict[str, Any]:
    """保留旧实现在此（已弃用；保留以便调用者 grep 到不迷惑）。"""
    if unit_text is None:
        return {"ok": False, "reason": "missing_unit"}

    unit_key = _normalize_unit(str(unit_text))
    if not unit_key:
        return {"ok": False, "reason": "empty_unit"}

    # 遍历所有 indicator 找到匹配该 unit 的 factor
    data = _load_dictionary()
    for slug, entry in data["indicators"].items():
        # 尝试精确匹配（原样），也尝试 NFKC 归一化后的键
        unit_alt = entry["unit_alt"]
        factor: float | None = None
        matched_key: str | None = None
        for k, v in unit_alt.items():
            if k == unit_text or _normalize_unit(k) == unit_key:
                factor = v
                matched_key = k
                break
        if factor is not None:
            try:
                raw = float(value)
            except (TypeError, ValueError) as e:
                return {"ok": False, "reason": f"invalid_value: {e}"}
            return {
                "ok": True,
                "slug": slug,
                "original_value": raw,
                "original_unit": matched_key,
                "canonical_value": raw * factor,
                "unit_si": entry["unit_si"],
                "factor": factor,
            }

    return {"ok": False, "reason": f"unknown_unit: {unit_text!r}"}


def normalize_reference_range(
    slug: str,
    value_si: float,
    stratum: str = "adult_male",
) -> dict[str, Any]:
    """按 slug + stratum 判定 value_si 是否落在参考区间内。

    参数:
      slug: canonical slug
      value_si: 已按 unit_si 表达的值
      stratum: adult_male / adult_female / pediatric / senior

    返回:
      {
        "slug": ...,
        "value": value_si,
        "unit_si": ...,
        "stratum": stratum,
        "ref_range": {"low": ..., "high": ...},
        "level": "low" | "normal" | "high",
        "in_range": bool,
      }
      slug 未知或 stratum 非法时 raise IndicatorDictError。
    """
    if stratum not in STRATA:
        raise IndicatorDictError(
            f"unknown stratum: {stratum!r}, expected one of {STRATA}"
        )
    entry = get_entry(slug)
    if entry is None:
        raise IndicatorDictError(f"unknown indicator slug: {slug!r}")

    rng = entry["ref_range"][stratum]
    low, high = float(rng["low"]), float(rng["high"])
    v = float(value_si)

    if v < low:
        level = _LEVEL_LOW
        in_range = False
    elif v > high:
        level = _LEVEL_HIGH
        in_range = False
    else:
        level = _LEVEL_NORMAL
        in_range = True

    return {
        "slug": slug,
        "value": v,
        "unit_si": entry["unit_si"],
        "stratum": stratum,
        "ref_range": {"low": low, "high": high},
        "level": level,
        "in_range": in_range,
    }


def is_loinc_code(code: str) -> bool:
    """判断是否为词典已收录的 LOINC code（字符串精确匹配）。"""
    if not code or not isinstance(code, str):
        return False
    return code in _loinc_index()


def invalidate_cache() -> None:
    """测试用：清缓存，重新解析 YAML。"""
    _load_dictionary.cache_clear()
    _alias_index.cache_clear()
    _loinc_index.cache_clear()
