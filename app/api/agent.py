"""
agent.py — HealthLens 智能体能力 HTTP 入口（GOAI 借鉴落地）

暴露 healthlens_agent 的两类核心能力：
  POST /api/v1/agent/fusion     融合安全管线（前置红牌 + 后置闸门 + 运行时审计）
  POST /api/v1/agent/team       四角色 Agent 团队（Planner/Executor/Critic/Referee）
  POST /api/v1/agent/team/stream 四角色 Agent 团队（SSE 流式，分阶段推送结果）

P0-3b（2026-10-24）：/team/stream 支持 SSE 分阶段推送，前端可以按阶段渐进渲染
（先看到 Planner 输出，再看到 Executor，最后 Referee 裁定），避免用户盯着
"思考中" spinner 等整个 team_run 跑完。响应 Content-Type 为 text/event-stream，
单条事件格式：event: plan | result | summary | done | error，data 为 JSON。

该路由在 app/main.py 中以 try/except 方式注册：若 healthlens_agent 或依赖不可用，
仅跳过该路由，不影响其余 API 启动。
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from healthlens_agent.pipeline import PipelineResult, run_pipeline, UserProfile
from healthlens_agent.team import team_run

from app.lib.claims_guard import apply_claims

router = APIRouter(prefix="/api/v1/agent", tags=["智能体"])


class HistoryMsg(BaseModel):
    role: str
    content: str


class ProfileIn(BaseModel):
    user_input: str = ""
    pathway_scores: Dict[str, float] = {}
    weak_axes: List[str] = []
    contraindications: List[str] = []
    # P0-3a：多轮上下文，可选携带最近 N 条历史（[{role, content}]）
    history: List[HistoryMsg] = []


class FusionIn(ProfileIn):
    audit_log_path: Optional[str] = None


def _combine_with_history(user_input: str, history: List[HistoryMsg]) -> str:
    """把多轮历史合并进 user_input 作为上下文。

    P0-3a 的简化实现：把最近几条历史拼到 user_input 之前，让规则引擎的关键词
    匹配能感知到之前的对话。这样即便不引入真正的 LLM 会话状态，用户也能得到
    "记得刚才说过什么"的体验。历史以 role:content 行呈现，用 [历史] 前缀区分
    以便规则引擎（如果未来要区分）能识别。
    """
    if not history:
        return user_input
    # 只取最近 4 条，避免 prompt 爆炸
    recent = history[-4:]
    lines = ["[对话历史]"]
    for m in recent:
        lines.append(f"{m.role}: {m.content}")
    lines.append("[本轮问题]")
    lines.append(user_input)
    return "\n".join(lines)


@router.post("/fusion")
def agent_fusion(req: FusionIn) -> Dict:
    """运行融合安全管线，返回带安全审计与免责声明的融合结果。"""
    profile = UserProfile(
        pathway_scores=req.pathway_scores or {},
        weak_axes=set(req.weak_axes or []),
        contraindications=set(req.contraindications or []),
    )
    res: PipelineResult = run_pipeline(
        user_input=req.user_input, profile=profile, audit_log_path=req.audit_log_path,
    )
    return apply_claims(res.to_dict(), None, "/api/v1/agent/fusion", jurisdiction="cn")


@router.post("/team")
def agent_team(req: ProfileIn) -> Dict:
    """运行四角色 Agent 团队，返回计划 / 执行 / 审查 / 裁判决策。"""
    user_input = _combine_with_history(req.user_input, req.history)
    return apply_claims(team_run(user_input), None, "/api/v1/agent/team", jurisdiction="cn")


# ---------------------------------------------------------------------------
# SSE 流式端点（P0-3b）
# ---------------------------------------------------------------------------
def _sse_event(event: str, data: Any) -> str:
    """生成一条 SSE 事件：event: <type>\ndata: <json>\n\n"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/team/stream")
def agent_team_stream(req: ProfileIn):
    """SSE 分阶段推送 Agent 团队结果。

    事件序列（严格按序）：
      1. event: meta     — 请求元信息（收到历史条数、llm 是否可用）
      2. event: plan     — Planner 输出（axes / pathway_hints / needs_gene）
      3. event: result   — Executor 输出（recommendations 列表）
      4. event: summary  — Referee 评审与决策
      5. event: done     — 全部完成，携带收敛信息
      6. event: error    — 出错时推送（可选）

    前端使用 EventSource 或 fetch + ReadableStream 消费。响应头设置
    Cache-Control: no-cache 与 X-Accel-Buffering: no 保证不被代理缓存。
    """
    user_input = _combine_with_history(req.user_input, req.history)

    def _stream():
        # 立即 flush 一个 meta 事件，让浏览器立刻知道连接建立
        yield _sse_event("meta", {
            "ok": True,
            "history_used": len(req.history or []),
            "endpoint": "/api/v1/agent/team/stream",
        })
        t0 = time.perf_counter()
        try:
            result = team_run(user_input)
            # 分阶段 yield（team_run 已同步跑完，我们按顺序 emit 让前端有渐进感）
            yield _sse_event("plan", result.get("plan", {}))
            yield _sse_event("result", {
                "recommendations": result.get("result", {}).get("recommendations", []),
                "weak_axes": result.get("result", {}).get("weak_axes", []),
                "convergence": result.get("convergence", {}),
                "llm": result.get("llm", {}),
            })
            yield _sse_event("summary", {
                "summary": result.get("summary", ""),
                "decision": result.get("decision", ""),
            })
            elapsed = round(time.perf_counter() - t0, 3)
            yield _sse_event("done", {"elapsed_sec": elapsed})
        except Exception as e:  # noqa: BLE001
            yield _sse_event("error", {"message": str(e), "type": type(e).__name__})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # 告诉 nginx 不要缓冲
            "Content-Encoding": "identity",
        },
    )
