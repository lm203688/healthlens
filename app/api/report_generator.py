"""
健康报告生成 API

对接 healthlens_agent 融合管线，生成完整的个性化健康评估报告。

端点：
- POST /api/v1/reports/generate  — 生成报告
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

router = APIRouter(prefix="/reports", tags=["报告生成"])


def _load_pipeline():
    spec = importlib.util.spec_from_file_location(
        "hl_pipeline", str(ROOT / "healthlens_agent" / "pipeline.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError("healthlens_agent/pipeline.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hl_pipeline"] = mod
    spec.loader.exec_module(mod)
    return mod


_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = _load_pipeline()
    return _pipeline


class ReportRequest(BaseModel):
    user_input: str = ""
    gene_scores: dict = {}
    user_id: str | None = None


@router.post("/generate")
async def api_generate_report(req: ReportRequest):
    """生成个性化健康评估报告。"""
    mod = _get_pipeline()
    from healthlens_agent.pipeline import UserProfile

    profile = UserProfile(pathway_scores=req.gene_scores)
    result = mod.run_pipeline(user_input=req.user_input, profile=profile)
    data = result.to_dict()

    return {
        "status": "ok",
        "report_id": f"RPT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": req.user_id,
        "report": data,
        "disclaimer": (
            "本报告由 HealthLens 基于整合医学稳态轴模型生成，"
            "结合中医古籍条文与现代基因通路研究，仅供参考，不构成医疗诊断或治疗建议。"
            "如有不适请及时就医。"
        ),
    }