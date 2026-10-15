"""证据层 L1 API —— L1-1/L1-2/L1-3（2026-10-15）

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L1

五个端点：
    POST /refute              → DoWhy refutation（三类 refuter）
    POST /individual-effect   → n-of-1 个体效应估计（paired bootstrap）
    POST /aggregate           → 贝叶斯层次聚合（多 n-of-1 汇总）
    POST /bandit/step         → 安全约束 bandit 决策
    GET  /bandit/status       → 当前 policy 状态

wellness 边界：全部 not_clinical=True；不使用诊断/治疗/患者/医疗词汇。
失败策略：输入越界返回 400，未知参数 fail-loud；dowhy/pymc 缺失时按
force_dowhy / force_pymc 决定是否抛 503。
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from app.lib.dowhy_adapter import (
    HealthLensUnavailableEngine,
    RefutationReport,
    do_dowhy_refutation,
)
from app.lib.nof_one_effect import (
    IndividualEffect,
    aggregate_effects,
    estimate_individual_effect,
)
from app.lib.safety_bandit import (
    SafetyBanditPolicy,
    build_policy,
)
from app.lib.wellness_simulator import LEVERS

router = APIRouter(tags=["证据层L1"])

# 全局单例：进程内一个 policy（多用户共享；生产多实例可挂 Redis）
_DEFAULT_POLICY: SafetyBanditPolicy | None = None


def _get_policy() -> SafetyBanditPolicy:
    global _DEFAULT_POLICY
    if _DEFAULT_POLICY is None:
        _DEFAULT_POLICY = build_policy(alpha=1.5, d=5, strict=True)
    return _DEFAULT_POLICY


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RefuteRequest(BaseModel):
    """DoWhy refutation 请求。"""
    baseline: dict[str, float] = Field(
        default_factory=dict, description="八轴基线分 {A..H: 0-100}")
    treatment: list[str] = Field(
        default_factory=list, description=f"生活方式杠杆，可选：{sorted(LEVERS)}")
    outcome: str | None = Field(default=None, description="结局变量名（默认 wellness_index）")
    data: dict[str, Any] | None = Field(default=None, description="保留：观测数据表")
    dowhy_mode: str = Field(
        default="auto", pattern=r"^(auto|dowhy|pure_python)$",
        description="auto=优先 dowhy，缺失降级；dowhy=强制，缺失抛 503；pure_python=纯 Python")
    weeks: int = Field(default=12, ge=1, le=52)
    lever_scale: float = Field(default=1.0, gt=0.0, le=2.0)
    placebo_n: int = Field(default=1000, ge=50, le=5000)
    common_cause_sigma: float = Field(default=1.5, ge=0.0, le=10.0)
    subset_fraction: float = Field(default=0.5, gt=0.0, le=1.0)


class IndividualEffectRequest(BaseModel):
    """n-of-1 个体效应估计请求。"""
    pre_scores: list[float] = Field(..., min_length=2, max_length=1000)
    post_scores: list[float] = Field(..., min_length=2, max_length=1000)
    ci_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    n_bootstrap: int = Field(default=10000, ge=100, le=100000)
    n_of_1_type: str = Field(
        default="Crossover", pattern=r"^(ABAB|Crossover|Cluster)$")
    point_estimate: float | None = Field(
        default=None, description="点估计，可选（若提供则跳过内部计算）")


class AggregateRequest(BaseModel):
    """贝叶斯层次聚合请求：多个 n-of-1 效应汇总。"""
    effects: list[float] = Field(..., min_length=1, max_length=500)
    se: list[float] | None = Field(default=None, description="每个效应的 SE（缺省 1.0）")
    group_ids: list[str] | None = Field(default=None)
    force_pymc: bool = Field(default=False, description="强制走 PyMC，缺失时抛 503")
    n_samples: int = Field(default=1000, ge=10, le=100000)


class BanditStepRequest(BaseModel):
    """安全约束 bandit 决策请求。"""
    user_context: dict[str, Any] = Field(
        default_factory=dict,
        description="用户上下文：pregnancy / medications / foods / biomarkers / jurisdiction")
    candidate_actions: list[dict[str, Any]] = Field(
        ..., min_length=1, max_length=50,
        description="候选动作列表：intervention / dose / herbs / formulas / endpoint")
    action_id_key: str = Field(default="intervention")


class BanditUpdateRequest(BaseModel):
    """Bandit reward 回传（可选，用于线上更新；此处只做状态查询）。"""
    action: dict[str, Any]
    reward: float


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/refute", response_model=dict)
async def post_refute(body: RefuteRequest):
    """DoWhy refutation：三类 refuter 汇总，输出因果效应的稳健性检验。"""
    if not body.treatment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="treatment 不可为空",
        )
    unknown = [t for t in body.treatment if t not in LEVERS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知杠杆 {unknown}；合法：{sorted(LEVERS)}",
        )
    try:
        report: RefutationReport = do_dowhy_refutation(
            simulator_baseline=body.baseline,
            treatment=body.treatment,
            outcome=body.outcome,
            data=body.data,
            dowhy_mode=body.dowhy_mode,
            weeks=body.weeks,
            lever_scale=body.lever_scale,
            placebo_n=body.placebo_n,
            common_cause_sigma=body.common_cause_sigma,
            subset_fraction=body.subset_fraction,
        )
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"engine_unavailable": str(exc), "pip_command": exc.pip_command},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.info(f"证据层 refutation | treatment={body.treatment} | method={report.method}")
    return report.summary()


@router.post("/individual-effect", response_model=dict)
async def post_individual_effect(body: IndividualEffectRequest):
    """n-of-1 个体效应估计：paired bootstrap + Cohen's d + E-value。"""
    if len(body.pre_scores) != len(body.post_scores):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"pre/post 长度不一致：{len(body.pre_scores)} vs {len(body.post_scores)}",
        )
    try:
        ie: IndividualEffect = estimate_individual_effect(
            pre_scores=body.pre_scores,
            post_scores=body.post_scores,
            ci_level=body.ci_level,
            n_bootstrap=body.n_bootstrap,
            n_of_1_type=body.n_of_1_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    result = ie.as_dict()
    # 顺手给出 E-value（借用 nof_one_effect.compute_evalue）
    from app.lib.nof_one_effect import compute_evalue
    try:
        se = ie.std_error if ie.std_error is not None else 0.0
        result["e_value"] = round(compute_evalue(ie.point_estimate, se), 4) if se > 0 else None
    except Exception:
        result["e_value"] = None
    logger.info(f"证据层 n-of-1 个体效应 | n={ie.sample_size} | type={ie.n_of_1_type}")
    return result


@router.post("/aggregate", response_model=dict)
async def post_aggregate(body: AggregateRequest):
    """贝叶斯层次聚合：多个 n-of-1 效应汇总到 pooled_effect。"""
    if len(body.effects) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="effects 不可为空",
        )
    if body.se is not None and len(body.se) != len(body.effects):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"se 长度 {len(body.se)} 与 effects {len(body.effects)} 不一致",
        )
    if body.group_ids is not None and len(body.group_ids) != len(body.effects):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"group_ids 长度 {len(body.group_ids)} 与 effects {len(body.effects)} 不一致",
        )
    try:
        result = aggregate_effects(
            effects=body.effects,
            se=body.se,
            group_ids=body.group_ids,
            force_pymc=body.force_pymc,
            n_samples=body.n_samples,
        )
    except HealthLensUnavailableEngine as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"engine_unavailable": str(exc), "pip_command": exc.pip_command},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.info(f"证据层聚合 | n={body.n_samples} | method={result.method}")
    return result.as_dict()


@router.post("/bandit/step", response_model=dict)
async def post_bandit_step(body: BanditStepRequest):
    """安全约束 bandit 决策：SafetyMask 前置 → LinUCB argmax。"""
    policy = _get_policy()
    try:
        result = policy.step(
            user_context=body.user_context,
            candidate_actions=body.candidate_actions,
            action_id_key=body.action_id_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.info(
        f"证据层 bandit step | n_actions={len(body.candidate_actions)} "
        f"| chosen={result.chosen_index}"
    )
    return result.as_dict()


@router.get("/bandit/status", response_model=dict)
async def get_bandit_status():
    """当前 policy 状态：bandit 已更新的次数、维度、alpha。"""
    policy = _get_policy()
    return policy.status()


@router.post("/bandit/update", response_model=dict)
async def post_bandit_update(body: BanditUpdateRequest):
    """回传一次 (action, reward) 到 bandit（在线学习，可选）。"""
    policy = _get_policy()
    policy.update(body.action, body.reward)
    return policy.status()
