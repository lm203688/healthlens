"""
agent.py — HealthLens 智能体能力 HTTP 入口（GOAI 借鉴落地）

暴露 healthlens_agent 的两类核心能力：
  POST /api/v1/agent/fusion  融合安全管线（前置红牌 + 后置闸门 + 运行时审计）
  POST /api/v1/agent/team    四角色 Agent 团队（Planner/Executor/Critic/Referee）

该路由在 app/main.py 中以 try/except 方式注册：若 healthlens_agent 或依赖不可用，
仅跳过该路由，不影响其余 API 启动。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from healthlens_agent.pipeline import PipelineResult, run_pipeline, UserProfile
from healthlens_agent.team import team_run

router = APIRouter(prefix="/api/v1/agent", tags=["智能体"])


class ProfileIn(BaseModel):
    user_input: str = ""
    pathway_scores: Dict[str, float] = {}
    weak_axes: List[str] = []
    contraindications: List[str] = []


class FusionIn(ProfileIn):
    audit_log_path: Optional[str] = None


@router.post("/fusion")
def agent_fusion(req: FusionIn) -> Dict:
    """运行融合安全管线，返回带安全审计与免责声明的融合结果。"""
    profile = UserProfile(
        pathway_scores=req.pathway_scores or None,
        weak_axes=set(req.weak_axes or []),
        contraindications=set(req.contraindications or []),
    )
    res: PipelineResult = run_pipeline(
        user_input=req.user_input, profile=profile, audit_log_path=req.audit_log_path,
    )
    return res.to_dict()


@router.post("/team")
def agent_team(req: ProfileIn) -> Dict:
    """运行四角色 Agent 团队，返回计划 / 执行 / 审查 / 裁判决策。"""
    return team_run(req.user_input)
