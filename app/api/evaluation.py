"""评估层 L4 API —— 5 个端点

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。

路由前缀：/api/v1/evaluation（app/__init__.py 已注册）

端点：
- POST /run-rubric       ：跑 rubric 评分（支持整份 benchmark 或指定 id 列表）
- POST /judge-answer     ：单个答案评分（rule 或 LLM）
- POST /ragas-check      ：RAGAS faithfulness（未装时抛 503）
- POST /biomni-query     ：Biomni 查询（未装时抛 503）
- POST /protocol-audit   ：跑 MCP+A2A 契约审计（L0）
- GET  /probe            ：探测 xgrammar / ragas / biomni 可用性

Wellness 平台术语纪律：仅做评估/审计，不做诊断/治疗建议。

作者：HealthLens L4 评估团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.lib.engine_exceptions import HealthLensUnavailableEngine
from app.lib.rubric_engine import RubricEngine

router = APIRouter()


# ─────────────────────────── Benchmark 加载 ───────────────────────────

_BENCHMARK_PATH_CANDIDATES = (
    "data/rubric_benchmark_v1.json",
    "/app/data/rubric_benchmark_v1.json",
    "/opt/healthlens/data/rubric_benchmark_v1.json",
)

_BENCHMARK_ENGINE: RubricEngine | None = None


def _get_engine() -> RubricEngine:
    """惰性加载 rubric engine（首次调用扫描盘）。"""
    global _BENCHMARK_ENGINE
    if _BENCHMARK_ENGINE is not None:
        return _BENCHMARK_ENGINE
    from pathlib import Path

    tried: list[str] = []
    for p in _BENCHMARK_PATH_CANDIDATES:
        pp = Path(p)
        tried.append(str(pp))
        if pp.is_file():
            engine = RubricEngine()
            try:
                engine.load_benchmark(pp)
                _BENCHMARK_ENGINE = engine
                return engine
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=500,
                    detail=f"benchmark load failed at {p}: {exc}",
                ) from exc
    raise HTTPException(
        status_code=500,
        detail=f"rubric_benchmark_v1.json not found. Tried: {tried}",
    )


# ─────────────────────────── 请求 / 响应模型 ───────────────────────────

class RunRubricRequest(BaseModel):
    """POST /run-rubric 请求体。"""

    item_ids: list[str] | None = Field(
        default=None,
        description="要跑哪些 rubric item id；None 表示跑全量",
    )
    answer: str = Field(..., min_length=1, description="被测答案文本")
    judge: Literal["rule", "llm"] = Field(default="rule", description="judge 类型")
    llm_model: str | None = Field(default=None, description="LLM judge 模型名（仅 judge=llm 时生效）")


class JudgeAnswerRequest(BaseModel):
    """POST /judge-answer 请求体。"""

    item_id: str = Field(..., min_length=1, description="rubric item id")
    answer: str = Field(..., min_length=1, description="被测答案")
    judge: Literal["rule", "llm"] = Field(default="rule")
    llm_model: str | None = Field(default=None)


class PairJudgeRequest(BaseModel):
    """支持 position swap 的请求（可选，用于 A/B 比较）。"""

    item_id: str
    answer_a: str
    answer_b: str
    judge: Literal["rule", "llm"] = "rule"
    llm_model: str | None = None


class RagasCheckRequest(BaseModel):
    """POST /ragas-check 请求体。"""

    answer: str = Field(..., min_length=1)
    context: str = Field(..., min_length=1)


class BiomniQueryRequest(BaseModel):
    """POST /biomni-query 请求体。"""

    claim: str = Field(..., min_length=1, description="生物医学 claim")


class ProtocolAuditRequest(BaseModel):
    """POST /protocol-audit 请求体。"""

    mcp_module_path: str | None = Field(
        default=None,
        description="MCP server 路径（默认 healthlens_agent/mcp_server.py）",
    )
    a2a_card_path: str | None = Field(
        default=None,
        description="agent-card 路径（默认 agent-card.json）",
    )


# ─────────────────────────── 通用响应模型 ───────────────────────────

class JudgeResultResponse(BaseModel):
    item_id: str
    score: float
    judge_type: str
    hits: list[str]
    misses: list[str]
    red_flag_hits: list[str]
    reasoning: str


class RubricRunResponse(BaseModel):
    total: int
    results: list[JudgeResultResponse]
    mean_score: float
    by_category: dict[str, dict[str, float]]


class ProbeResponse(BaseModel):
    engines: list[dict[str, Any]]


# ─────────────────────────── 端点 ───────────────────────────

@router.post(
    "/run-rubric",
    response_model=RubricRunResponse,
    summary="跑 rubric 评分",
    description=(
        "对给定 answer 跑 rubric 评分。item_ids=None 时跑 benchmark 全量；"
        "judge='rule' 走确定性规则，'llm' 走 SenseNova（需 SENSENOVA_API_KEY）。"
        "报告：HealthLens_下一阶段愿景与跃迁方案_2026-10-15 §5 L4。"
    ),
)
def run_rubric(req: RunRubricRequest) -> RubricRunResponse:
    engine = _get_engine()
    if req.item_ids:
        missing = [i for i in req.item_ids if i not in engine.items]
        if missing:
            raise HTTPException(status_code=400, detail=f"unknown item_ids: {missing}")
        target_ids = req.item_ids
    else:
        target_ids = list(engine.items.keys())

    results: list[JudgeResultResponse] = []
    by_category: dict[str, dict[str, list[float]]] = {}
    for iid in target_ids:
        item = engine.get_item(iid)
        try:
            r = _dispatch_judge(engine, req.answer, item, req.judge, req.llm_model)
        except HealthLensUnavailableEngine as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        results.append(_result_to_response(r))
        cat_bucket = by_category.setdefault(item.category, {"scores": []})
        cat_bucket["scores"].append(r.score)

    mean_score = sum(r.score for r in results) / len(results) if results else 0.0
    by_cat_out: dict[str, dict[str, float]] = {
        cat: {
            "count": len(data["scores"]),
            "mean_score": sum(data["scores"]) / len(data["scores"]),
        }
        for cat, data in by_category.items()
    }
    return RubricRunResponse(
        total=len(results),
        results=results,
        mean_score=round(mean_score, 4),
        by_category=by_cat_out,
    )


@router.post(
    "/judge-answer",
    response_model=JudgeResultResponse,
    summary="单个答案评分",
    description="对单个 rubric item 用指定 judge 类型评分。",
)
def judge_answer(req: JudgeAnswerRequest) -> JudgeResultResponse:
    engine = _get_engine()
    try:
        item = engine.get_item(req.item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"item not found: {req.item_id}") from exc
    try:
        r = _dispatch_judge(engine, req.answer, item, req.judge, req.llm_model)
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _result_to_response(r)


@router.post(
    "/judge-answer/pair",
    summary="A/B 位置交换 judge（消除位置偏差）",
    description=(
        "对同一 rubric item 的两个答案做位置交换 judge，返回 mean_scores / position_bias / winner。"
        "报告：HealthLens_下一阶段愿景与跃迁方案_2026-10-15 §5 L4。"
    ),
)
def judge_answer_pair(req: PairJudgeRequest) -> dict[str, Any]:
    engine = _get_engine()
    try:
        item = engine.get_item(req.item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"item not found: {req.item_id}") from exc
    if req.judge == "rule":
        judge_fn = engine.rule_judge
    elif req.judge == "llm":
        try:
            judge_fn = lambda a, it: engine.llm_judge(a, it, model=req.llm_model or "sensechat-plus")  # noqa: E731
        except HealthLensUnavailableEngine as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=400, detail=f"unknown judge: {req.judge}")
    try:
        return engine.position_swap_judge(req.answer_a, req.answer_b, item, judge_fn=judge_fn)
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/ragas-check",
    summary="RAGAS faithfulness 检查",
    description=(
        "用 RAGAS faithfulness metric 评估 answer 是否忠于 context。"
        "未装 ragas 时返回 503；可考虑用 fallback_faithfulness 做粗略 baseline。"
    ),
)
def ragas_check(req: RagasCheckRequest) -> dict[str, Any]:
    from app.lib import ragas_adapter

    try:
        score = ragas_adapter.faithfulness_check(req.answer, req.context)
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "answer": req.answer,
        "context_length": len(req.context),
        "faithfulness": score,
        "engine": "ragas",
        "note": "RAGAS 真值",
    }


@router.post(
    "/biomni-query",
    summary="Biomni 外部证据查询",
    description=(
        "调用 Biomni 查询生物医学 claim 的外部证据。"
        "Biomni 未装时返回 503（报告 §5 L4 指出其可能未公开发布）。"
    ),
)
def biomni_query(req: BiomniQueryRequest) -> dict[str, Any]:
    from app.lib import biomni_adapter

    try:
        return biomni_adapter.query_biomedical_claim(req.claim)
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/protocol-audit",
    summary="L0 协议审计（MCP 2026-07-28 + A2A v1.0.1）",
    description=(
        "对 mcp_server.py 和 agent-card.json 做静态 AST 审计，返回 13 项 check 结果。"
        "L0 审计**只做检测和报告**，不做自动修复。"
    ),
)
def protocol_audit(req: ProtocolAuditRequest | None = None) -> dict[str, Any]:
    from app.lib import protocol_audit as audit_mod

    try:
        return audit_mod.run_full_audit(
            mcp_module_path=req.mcp_module_path if req else None,
            a2a_card_path=req.a2a_card_path if req else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"audit failed: {exc}") from exc


@router.get(
    "/probe",
    response_model=ProbeResponse,
    summary="探测 L4 引擎可用性",
    description="返回 xgrammar / ragas / biomni 是否可 import，供外部自检。",
)
def probe() -> ProbeResponse:
    from app.lib import biomni_adapter, ragas_adapter, structured_output

    engines = [
        structured_output.probe(),
        ragas_adapter.probe(),
        biomni_adapter.probe(),
    ]
    return ProbeResponse(engines=engines)


# ─────────────────────────── 内部工具 ───────────────────────────

def _dispatch_judge(engine: RubricEngine, answer: str, item, judge: str, llm_model: str | None):
    if judge == "rule":
        return engine.rule_judge(answer, item)
    if judge == "llm":
        return engine.llm_judge(answer, item, model=llm_model or "sensechat-plus")
    raise ValueError(f"unknown judge type: {judge}")


def _result_to_response(r) -> JudgeResultResponse:
    return JudgeResultResponse(
        item_id=r.item_id,
        score=r.score,
        judge_type=getattr(r, "judge_type", "unknown"),
        hits=r.hits,
        misses=r.misses,
        red_flag_hits=r.red_flag_hits,
        reasoning=r.reasoning,
    )


__all__ = ["router"]
