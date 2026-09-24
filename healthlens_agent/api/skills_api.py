"""
Skill 注册表 API

端点：
- GET    /api/v1/skills              — 列出所有 Skill
- GET    /api/v1/skills/{name}       — 获取 Skill 详情
- POST   /api/v1/skills/{name}/run   — 执行 Skill
- POST   /api/v1/skills/{name}/test  — 测试 Skill
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

router = APIRouter(prefix="/skills", tags=["技能中心"])

# 延迟加载 healthlens_agent.skills
def _load_skills_module():
    spec = importlib.util.spec_from_file_location(
        "hl_skills", str(ROOT / "healthlens_agent" / "skills.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("healthlens_agent/skills.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hl_skills"] = mod
    spec.loader.exec_module(mod)
    return mod


_skills = None


def _get_skills():
    global _skills
    if _skills is None:
        _skills = _load_skills_module()
    return _skills


class SkillRunRequest(BaseModel):
    kwargs: dict[str, Any] = {}


@router.get("")
async def api_list_skills():
    """列出所有可用的 Skill。"""
    mod = _get_skills()
    return {"skills": mod.list_skills()}


@router.get("/{name}")
async def api_skill_info(name: str):
    """获取单个 Skill 的详细信息。"""
    mod = _get_skills()
    info = mod.skill_info(name)
    if info is None:
        raise HTTPException(404, f"Skill '{name}' 不存在")
    return info


@router.post("/{name}/run")
async def api_run_skill(name: str, req: SkillRunRequest):
    """执行指定 Skill。"""
    mod = _get_skills()
    info = mod.skill_info(name)
    if info is None:
        raise HTTPException(404, f"Skill '{name}' 不存在")
    try:
        result = mod.run_skill(name, **req.kwargs)
        return {"status": "ok", "skill": name, "result": result}
    except Exception as exc:
        raise HTTPException(500, f"Skill 执行失败: {exc}")


@router.post("/{name}/test")
async def api_test_skill(name: str):
    """运行 Skill 的 test.py。"""
    mod = _get_skills()
    try:
        result = mod.test_skill(name)
        return result
    except Exception as exc:
        raise HTTPException(500, f"Skill 测试失败: {exc}")