"""
_loader.py — 按需加载真实融合引擎 app/lib/fusion_engine.py

背景：app 包在 __init__ 时依赖 fastapi（部署环境有，本地/CI 精简环境未必有）。
本库是无重型依赖的"安全/多 Agent/评测"层，因此用 importlib 直接加载
fusion_engine 模块（它自身只依赖标准库），绕过 app 包的 fastapi 依赖。
结果缓存到 sys.modules，避免重复加载。
"""

from __future__ import annotations

import importlib.util
import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PKG_DIR)  # 仓库根目录
_FE_PATH = os.path.join(_ROOT, "app", "lib", "fusion_engine.py")

_cached = None


def load_fusion_engine():
    """加载并返回 fusion_engine 模块（带缓存）。"""
    global _cached
    existing = sys.modules.get("fusion_engine")
    if existing is not None and hasattr(existing, "recommend"):
        return existing
    if _cached is not None:
        return _cached
    if not os.path.exists(_FE_PATH):
        raise FileNotFoundError(
            f"未找到融合引擎：{_FE_PATH}。请确认 healthlens_agent 位于仓库根目录。"
        )
    spec = importlib.util.spec_from_file_location("fusion_engine", _FE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fusion_engine"] = mod  # 预注册，避免模块内相对导入问题
    spec.loader.exec_module(mod)
    _cached = mod
    return mod


def repo_root() -> str:
    return _ROOT
