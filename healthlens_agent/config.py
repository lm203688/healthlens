"""
HealthLens 配置中心

从 data/healthlens_config.json 加载所有可调参数，
支持运行时覆盖（环境变量 / 运行时注入）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "healthlens_config.json"
_ENV_PREFIX = "HL_CONFIG"


def _load_defaults() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _apply_env_overrides(config: dict) -> dict:
    """HL_CONFIG_SECTION_KEY=value 形式覆盖配置。"""
    for key, value in os.environ.items():
        if key.startswith(_ENV_PREFIX + "_"):
            parts = key[len(_ENV_PREFIX) + 1:].split("_")
            if len(parts) < 2:
                continue
            section, key_name = parts[0].lower(), parts[1].lower()
            if section not in config:
                config[section] = {}
            config[section][key_name] = value
    return config


class Config:
    _instance = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._data = _apply_env_overrides(_load_defaults())
        return cls._instance

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return self._data.get(section, default)
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value

    def reload(self) -> None:
        self._data = _apply_env_overrides(_load_defaults())

    def to_dict(self) -> dict:
        return self._data

    def __repr__(self) -> str:
        return "Config({k: '...' for k in self._data})"


def get_config() -> Config:
    return Config()


# 常用快捷访问
def axes_config() -> dict:
    return get_config().get("axes", {})


def safety_config() -> dict:
    return get_config().get("safety", {})


def llm_config() -> dict:
    return get_config().get("llm", {})


def fusion_config() -> dict:
    return get_config().get("fusion", {})
