"""联邦证据网络 API（L3 联邦层）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3。
> 「L3 联邦证据网络（3–6 月）— 最锋利的原创点」
> 「个体数据不出域 + 只共享充分统计量」；「贝叶斯层次聚合 + 联邦目标试验仿真」。

路由前缀：/api/v1/federated（在 app/__init__.py 里注册）

端点：
- POST /stats                    ：接收单个 tenant 的 SufficientStats → 校验 → 存内存 dict → 返回 hash
- POST /aggregate                ：跨所有已注册 tenant 调用 HierarchicalAggregator.aggregate()
- GET  /tenants                  ：列出 tenant_id + hash（**不含个体数据**）
- POST /trial/run                ：接收 TargetTrialSpec → TargetTrialEmulator.emulate() + refutation
- GET  /trial/status/{trial_id}  ：查询 trial 进度（内存 dict；生产应接 DB）
- GET  /export/posterior/{tenant_id} ：导出该 tenant 的聚合后验

Wellness 平台术语纪律：本层只做跨机构充分统计量聚合与效应估计，
不做诊断/治疗建议、不做个体级推断；明确不承诺 DP。

作者：HealthLens L3 联邦层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.lib.federated import (
    AggregationResult,
    HealthLensUnavailableEngine,
    HierarchicalAggregator,
    SufficientStats,
    TargetTrialEmulator,
    TargetTrialSpec,
    hash_stats,
    validate_tenant_payload,
)


router = APIRouter()


# ─────────────────────────── 请求 / 响应模型 ───────────────────────────


class StatsRequest(BaseModel):
    """POST /stats 请求体：单个租户的充分统计量。

    字段集合与 `SufficientStats` dataclass 对齐；协议层硬性拒绝 raw samples。
    """

    tenant_id: str = Field(..., min_length=1, description="租户唯一标识")
    # 数值越界（n<=0 / var<0 / effect_se<=0）统一由协议层 `validate_tenant_payload`
    # 返回 400 + violations 清单；Pydantic 只挡基础类型，避免被 422 提前拦截。
    n: int = Field(..., description="n-of-1 队列人数（正整数，协议层校验）")
    mean: float = Field(..., description="outcome 均值")
    var: float = Field(..., description="outcome 方差（协议层校验非负）")
    effect_estimate: float = Field(..., description="局部处理效应点估计")
    effect_se: float = Field(..., description="局部处理效应标准误（协议层校验正数）")
    covariate_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="分层维度（region/age-band/gender/axis 等）聚合统计",
    )


class StatsResponse(BaseModel):
    """POST /stats 响应体。"""

    tenant_id: str
    sha256: str
    n: int
    method: str = "sufficient_stats_protocol"


class AggregationRequest(BaseModel):
    """POST /aggregate 请求体（可选参数）。"""

    method: str = Field(
        default="empirical_bayes",
        pattern=r"^(empirical_bayes|monte_carlo)$",
        description="聚合方法：empirical_bayes（默认）或 monte_carlo（fallback）",
    )


class TenantsResponse(BaseModel):
    """GET /tenants 响应体：不含个体数据，仅 hash 与规模。"""

    tenants: list[dict[str, Any]]
    n_tenants: int


class TrialRunRequest(BaseModel):
    """POST /trial/run 请求体：TargetTrialSpec + 参与租户列表。"""

    intervention: str = Field(..., min_length=1, description="干预描述")
    comparator: str = Field(..., min_length=1, description="对照描述")
    eligibility_criteria: dict[str, Any] = Field(default_factory=dict)
    assignment: str = Field(
        default="as_treated",
        pattern=r"^(randomized|as_treated|switcher)$",
        description="分配机制",
    )
    outcome: str = Field(default="effect_estimate", min_length=1)
    follow_up_window: int = Field(default=8, gt=0, description="随访窗口（week）")
    tenant_ids: list[str] | None = Field(
        default=None,
        description="参与试验的租户白名单；None = 全体已注册",
    )
    max_weight: float = Field(default=20.0, gt=0, description="IPW 权重上截断")
    trim_fraction: float = Field(default=0.01, ge=0, lt=1, description="IPW 下截断")


class TrialStatusResponse(BaseModel):
    """GET /trial/status/{trial_id} 响应体。"""

    trial_id: str
    found: bool
    status: str | None = None
    spec: dict[str, Any] | None = None
    estimate: float | None = None
    n_tenants: int | None = None
    note: str = "in-memory dict (dev only); production should use DB"


class PosteriorExportResponse(BaseModel):
    """GET /export/posterior/{tenant_id} 响应体。"""

    tenant_id: str
    found: bool
    posterior: dict[str, Any] | None = None
    note: str


# ─────────────────────────── 内存注册表（dev only） ───────────────────────────


# 生产环境应接 DB / Redis；此 dict 仅用于本地开发与冒烟测试。
# 报告定位：hash 幂等 + 跨机构聚合对齐；进程重启即丢失。
_REGISTRY: dict[str, SufficientStats] = {}
_LAST_AGGREGATION: dict[str, AggregationResult] = {}  # tenant_id -> 该 tenant 的聚合结果
_TRIAL_REGISTRY: dict[str, dict[str, Any]] = {}


def _reset_state() -> None:
    """测试用：清空内存注册表（生产不调用）。"""
    _REGISTRY.clear()
    _LAST_AGGREGATION.clear()
    _TRIAL_REGISTRY.clear()


def _result_to_dict(result: AggregationResult) -> dict[str, Any]:
    """把 AggregationResult dataclass 序列化为 JSON-safe dict。"""
    return asdict(result)


def _build_stats(payload: StatsRequest) -> SufficientStats:
    """从请求体构造 SufficientStats，先走协议层校验（fail-loud）。

    协议层 `validate_tenant_payload` 是"个体数据不出域"承诺的代码级闸门；
    Pydantic 只挡基础类型，深层违规（list-of-list、raw_samples 键）在这里兜住。
    """
    raw: dict[str, Any] = payload.model_dump()
    violations = validate_tenant_payload(raw)
    if violations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "sufficient_stats_validation_failed",
                "violations": violations,
                "reference": "§5 L3 「个体数据不出域 + 只共享充分统计量」",
            },
        )
    return SufficientStats(
        tenant_id=raw["tenant_id"],
        n=int(raw["n"]),
        mean=float(raw["mean"]),
        var=float(raw["var"]),
        effect_estimate=float(raw["effect_estimate"]),
        effect_se=float(raw["effect_se"]),
        covariate_summary=raw.get("covariate_summary") or {},
    )


# ─────────────────────────── 端点 ───────────────────────────


@router.post(
    "/stats",
    response_model=StatsResponse,
    summary="接收单个租户的充分统计量",
    description=(
        "接收 `SufficientStats` → 协议层校验 → 存内存 dict → 返回 sha256 内容寻址哈希。"
        "**协议层硬性拒绝 raw samples**（键名 / 值形态 / 深层嵌套一律拒绝）。"
        "报告：HealthLens_下一阶段愿景与跃迁方案_2026-10-15 §5 L3。"
    ),
)
def submit_stats(req: StatsRequest) -> StatsResponse:
    stats = _build_stats(req)
    sha = hash_stats(stats)
    _REGISTRY[stats.tenant_id] = stats
    return StatsResponse(
        tenant_id=stats.tenant_id,
        sha256=sha,
        n=stats.n,
    )


@router.post(
    "/aggregate",
    summary="跨所有已注册租户进行贝叶斯层次聚合",
    description=(
        "调用 `HierarchicalAggregator.aggregate()`，返回 `AggregationResult`。"
        "空集返回 `{n_tenants: 0, warning: 'no tenants registered'}`。"
        "结果回写到 per-tenant 后验，供 `/export/posterior/{tenant_id}` 查询。"
        "报告：§5 L3 中心贝叶斯层次聚合（Donner & Klietz 2006）。"
    ),
)
def aggregate_endpoint(req: AggregationRequest) -> dict[str, Any]:
    if not _REGISTRY:
        return {
            "success": True,
            "data": {"n_tenants": 0, "warning": "no tenants registered"},
        }
    stats_list = list(_REGISTRY.values())
    aggregator = HierarchicalAggregator()
    try:
        result = aggregator.aggregate(stats_list, method=req.method)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"aggregation failed: {exc}") from exc

    # 记录 per-tenant 后验：tenant 拿到全局聚合结果（region 隔离在 fabric 层做，
    # 此处 aggregate 直接对全体租户跑；如需 region 隔离应通过 fabric.run_round）。
    for tid in _REGISTRY.keys():
        _LAST_AGGREGATION[tid] = result

    return {
        "success": True,
        "data": {
            **_result_to_dict(result),
            "per_tenant_stats_count": len(stats_list),
            "method": req.method,
        },
    }


@router.get(
    "/tenants",
    response_model=TenantsResponse,
    summary="列出已注册租户（不含个体数据）",
    description=(
        "返回 tenant_id、sha256 hash、n（规模指标）。"
        "**不返回任何 raw samples 或个体级字段**——响应字段集合在协议层锁定。"
    ),
)
def list_tenants() -> TenantsResponse:
    tenants = [
        {"tenant_id": tid, "sha256": hash_stats(s), "n": int(s.n)}
        for tid, s in _REGISTRY.items()
    ]
    return TenantsResponse(tenants=tenants, n_tenants=len(tenants))


@router.post(
    "/trial/run",
    summary="联邦目标试验仿真",
    description=(
        "接收 `TargetTrialSpec` + 参与租户白名单，调用 `TargetTrialEmulator.emulate()` "
        "与 `run_refutation()`（placebo intervention + random assignment 双重反证）。"
        "报告：§5 L3「联邦目标试验仿真（npj Digit Med 2025;8:387 简化版）」。"
    ),
)
def run_trial(req: TrialRunRequest) -> dict[str, Any]:
    if req.tenant_ids is None:
        tenant_stats = list(_REGISTRY.values())
    else:
        missing = [t for t in req.tenant_ids if t not in _REGISTRY]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tenant_ids: {missing}",
            )
        tenant_stats = [_REGISTRY[t] for t in req.tenant_ids]

    if not tenant_stats:
        return {
            "success": True,
            "data": {"warning": "no tenants available for trial", "n_tenants": 0},
        }

    spec = TargetTrialSpec(
        intervention=req.intervention,
        comparator=req.comparator,
        eligibility_criteria=req.eligibility_criteria,
        assignment=req.assignment,
        outcome=req.outcome,
        follow_up_window=req.follow_up_window,
    )
    emulator = TargetTrialEmulator(
        ipw={"trim_fraction": req.trim_fraction, "max_weight": req.max_weight}
    )
    try:
        estimate = emulator.emulate(spec, tenant_stats)
        refutation = emulator.run_refutation(spec, tenant_stats)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"trial failed: {exc}") from exc

    trial_id = f"trial_{uuid.uuid4().hex[:12]}"
    _TRIAL_REGISTRY[trial_id] = {
        "status": "done",
        "spec": estimate["spec"],
        "estimate": estimate["estimate"],
        "n_tenants": estimate["n_tenants"],
    }

    return {
        "success": True,
        "data": {
            "trial_id": trial_id,
            "estimate": estimate,
            "refutation": refutation,
            "ipw_config": {
                "trim_fraction": req.trim_fraction,
                "max_weight": req.max_weight,
            },
        },
    }


@router.get(
    "/trial/status/{trial_id}",
    response_model=TrialStatusResponse,
    summary="查询目标试验进度",
    description=(
        "查询指定 trial_id 的状态。**当前实现：进程内 dict，重启即丢失。** "
        "生产应接 DB（报告 §5 L3：跨机构 trial 审计链需要持久化）。"
    ),
)
def trial_status(trial_id: str) -> TrialStatusResponse:
    if not trial_id:
        raise HTTPException(status_code=400, detail="trial_id must be nonempty")
    entry = _TRIAL_REGISTRY.get(trial_id)
    return TrialStatusResponse(
        trial_id=trial_id,
        found=entry is not None,
        status=entry.get("status") if entry else None,
        spec=entry.get("spec") if entry else None,
        estimate=entry.get("estimate") if entry else None,
        n_tenants=entry.get("n_tenants") if entry else None,
    )


@router.get(
    "/export/posterior/{tenant_id}",
    response_model=PosteriorExportResponse,
    summary="导出指定租户的聚合后验",
    description=(
        "返回该 tenant 最近一次 `/aggregate` 结果中的后验摘要。"
        "未跑过聚合时返回 `found=False` + 明确提示先调 `/aggregate`。"
        "响应不含个体级字段——只回传充分统计量的聚合结果。"
    ),
)
def export_posterior(tenant_id: str) -> PosteriorExportResponse:
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id must be nonempty")
    result = _LAST_AGGREGATION.get(tenant_id)
    if result is None:
        return PosteriorExportResponse(
            tenant_id=tenant_id,
            found=False,
            posterior=None,
            note=(
                "no aggregation recorded for this tenant; "
                "call POST /api/v1/federated/aggregate first"
            ),
        )
    return PosteriorExportResponse(
        tenant_id=tenant_id,
        found=True,
        posterior=_result_to_dict(result),
        note="posterior from most recent cross-tenant aggregation (in-memory)",
    )
