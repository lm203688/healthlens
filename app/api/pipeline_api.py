"""
Unified pipeline API — agent-lib + health-agent + data-flow.

端点：
- GET    /api/v1/pipeline/phases      — 列出所有管线阶段（统一注册表）
- GET    /api/v1/pipeline/status      — 管线运行状态
- POST   /api/v1/pipeline/phase/{id}/run  — 执行单个阶段
- POST   /api/v1/pipeline/run-all       — 执行全部数据流阶段
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

router = APIRouter(prefix="/pipeline", tags=["自动化管线"])


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"hl_{name}", str(ROOT / "healthlens_agent" / f"{name}.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"healthlens_agent/{name}.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"hl_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_api = None
_registry = None


def _get_api():
    global _api
    if _api is None:
        _api = _load("auto_pipeline")
    return _api


def _get_registry():
    global _registry
    if _registry is None:
        _registry = _load("pipeline_registry")
    return _registry


class RunPhaseRequest(BaseModel):
    dry_run: bool = False
    inputs: dict[str, Any] = {}


@router.get("/phases")
async def api_list_phases():
    """Unified phase list from pipeline_registry."""
    reg = _get_registry()
    return {"phases": reg.list_all_phases(), "count": len(reg.list_all_phases())}


@router.get("/status")
async def api_pipeline_status():
    mod = _get_api()
    return mod.get_pipeline_status()


@router.post("/phase/{phase_id}/run")
async def api_run_phase(phase_id: str, req: RunPhaseRequest):
    reg = _get_registry()
    handler = reg.get_handler(phase_id)
    result = handler(inputs=req.inputs)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error", "执行失败"))
    return result


@router.post("/run-all")
async def api_run_all(req: RunPhaseRequest):
    mod = _get_api()
    results = mod.run_all(dry_run=req.dry_run)
    return {"status": "done", "results": results}
