"""
HealthLens Skill 注册表与执行器

对接 skills/scaffold.py 的 SkillRegistry，提供：
- list_skills()  返回所有已发现的 Skill 元信息
- run_skill(name, **kwargs)  执行指定 Skill 并返回结果
- test_skill(name)  运行 Skill 的 test.py
- skill_info(name)  返回单个 Skill 的详细信息
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills"

# 延迟加载 scaffold（避免 FastAPI 依赖问题）
def _load_registry():
    spec = importlib.util.spec_from_file_location(
        "skills_scaffold", str(SKILL_DIR / "scaffold.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("skills/scaffold.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skills_scaffold"] = mod
    spec.loader.exec_module(mod)
    return mod


_registry = None


def get_registry():
    global _registry
    if _registry is None:
        mod = _load_registry()
        _registry = mod._registry
    return _registry


def list_skills() -> list[dict]:
    reg = get_registry()
    manifests = reg.discover()
    return [m.to_dict() for m in manifests]


def run_skill(name: str, **kwargs: Any) -> dict:
    reg = get_registry()
    return reg.execute(name, **kwargs)


def test_skill(name: str) -> dict:
    reg = get_registry()
    return reg.test(name)


def skill_info(name: str) -> dict | None:
    reg = get_registry()
    m = reg.get(name)
    return m.to_dict() if m else None
