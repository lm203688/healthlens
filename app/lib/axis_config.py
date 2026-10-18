"""八轴阈值配置加载器（A2 参数外置）

**核心命题**：改 YAML 即改行为，无需发版；法域差异化支持。

**加载优先级**：
    1. jurisdiction_overrides[jurisdiction][axis][threshold]
    2. thresholds[axis][metric][default]
    3. axis_scorers.py 硬编码 fallback（配置加载失败时）

**用法**：
    from app.lib.axis_config import get_thresholds, get_axis_config, get_threshold
    t = get_thresholds(jurisdiction="cn")
    hba1c_max = t["axis_a"]["hba1c"]["impaired_max"]  # 6.5
    axis_meta = get_axis_config("A")
    val = get_threshold("A", "hba1c", "impaired_max", jurisdiction="cn", default=6.5)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "axes" / "axes.yaml"

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_loaded_config: dict | None = None


class AxisConfigError(RuntimeError):
    """配置加载失败。axis_scorers 会自动 fallback 到硬编码值。"""


def _load_yaml() -> dict:
    """加载 YAML 配置，异常时返回空 dict（调用方 fallback）。"""
    global _loaded_config
    if _loaded_config is not None:
        return _loaded_config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _loaded_config = yaml.safe_load(f) or {}
        logger.info(f"Loaded axis config from {CONFIG_PATH}")
    except FileNotFoundError:
        logger.warning(f"Axis config not found: {CONFIG_PATH}, using fallback values")
        _loaded_config = {}
    except Exception as e:
        logger.error(f"Failed to load axis config: {e}, using fallback values")
        _loaded_config = {}
    return _loaded_config


def reload_config() -> None:
    """清空缓存，重新加载磁盘配置（部署时用）。"""
    global _loaded_config
    _loaded_config = None
    _cache.clear()


def get_thresholds(jurisdiction: str = "cn") -> dict:
    """获取指定法域的八轴阈值配置。

    Returns:
        合并 default + jurisdiction_overrides 后的完整阈值 dict。
        加载失败时返回空 dict（调用方需 fallback 到硬编码）。
    """
    key = f"thresholds_{jurisdiction.lower()}"
    if key in _cache:
        return _cache[key]

    config = _load_yaml()
    if not config:
        return {}

    with _cache_lock:
        if key in _cache:
            return _cache[key]

        merged: dict[str, Any] = {}
        for axis_key, axis_cfg in config.items():
            if not axis_key.startswith("axis_"):
                continue
            if not isinstance(axis_cfg, dict):
                continue
            merged[axis_key] = {
                "label": axis_cfg.get("label"),
                "concept": axis_cfg.get("concept"),
                "proxy": axis_cfg.get("proxy"),
                "thresholds": {},
            }
            for metric, vals in axis_cfg.get("thresholds", {}).items():
                if isinstance(vals, dict) and "default" in vals:
                    merged[axis_key]["thresholds"][metric] = dict(vals["default"])

        overrides = config.get("jurisdiction_overrides", {}).get(jurisdiction.lower(), {})
        for axis_key, axis_overrides in overrides.items():
            if axis_key in merged and isinstance(axis_overrides, dict):
                for metric, vals in axis_overrides.get("thresholds", {}).items():
                    if metric in merged[axis_key]["thresholds"] and isinstance(vals, dict):
                        merged[axis_key]["thresholds"][metric].update(vals)

        _cache[key] = merged
        return merged


def get_axis_config(axis_letter: str) -> dict:
    """获取单个轴的元数据（label/concept/proxy）。"""
    axis_key = f"axis_{axis_letter.lower()}"
    defaults = {
        "A": {"label": "气化-自噬(AMPK-mTOR)", "concept": "气/气化", "proxy": "血糖代谢稳态"},
        "B": {"label": "气血-线粒体能量(NAD+/mtDNA)", "concept": "气血", "proxy": "线粒体能量代谢"},
        "C": {"label": "络脉-内皮微循环", "concept": "络脉", "proxy": "血管内皮与微循环"},
        "D": {"label": "阴阳-昼夜节律", "concept": "阴阳", "proxy": "昼夜节律稳态"},
        "E": {"label": "脏腑-神经内分泌(HPA)", "concept": "脏腑", "proxy": "HPA 轴与应激稳态"},
        "F": {"label": "正邪-炎症负荷", "concept": "正邪", "proxy": "慢性低度炎症"},
        "G": {"label": "神-情志(自主神经)", "concept": "神", "proxy": "自主神经平衡"},
        "H": {"label": "先天-肾精(表观遗传)", "concept": "先天之本", "proxy": "表观遗传完整性"},
    }
    fallback = defaults.get(axis_letter.upper(), {})

    config = _load_yaml()
    if not config or axis_key not in config:
        return fallback

    cfg = config[axis_key]
    return {
        "label": cfg.get("label", fallback.get("label")),
        "concept": cfg.get("concept", fallback.get("concept")),
        "proxy": cfg.get("proxy", fallback.get("proxy")),
    }


def get_threshold(
    axis_letter: str,
    metric: str,
    key: str,
    jurisdiction: str = "cn",
    default: float | None = None,
) -> float | None:
    """获取单个阈值的具体值（最细粒度接口）。"""
    axis_key = f"axis_{axis_letter.lower()}"
    thresholds = get_thresholds(jurisdiction)
    try:
        return thresholds[axis_key]["thresholds"][metric][key]
    except (KeyError, TypeError):
        return default


def config_loaded() -> bool:
    """检查 YAML 配置是否成功加载。"""
    return bool(_load_yaml())
