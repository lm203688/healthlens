"""因果推演 API — S2-1（2026-10-13）

把 wellness_simulator 的确定性耦合网络升级为**因果推断装置**（SCM / 反事实 /
校准 / E-value 敏感性），对外暴露为端点。设计约束与 causal_simulator 一致：

- 全程 not_clinical / 虚拟推演，不构成任何诊断、治疗或个体结果预测。
- 耦合系数为透明启发式（文献锚定），**非因果识别量**；sensitivity 的诚实结论
  正是「须经前瞻队列（S2-2 / S4）标定」。
- fail-loud：输入越界返回 400，绝不静默降级产出「看起来正常」的结果。
- 结构类端点（/scm /sensitivity /levers）公开；个性化推演（counterfactual /
  calibrate /report）需登录，与 /axes/project 一致。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from loguru import logger

from app.models.user import User
from app.api.deps import get_current_user
from app.lib.wellness_simulator import AXES, AXIS_LABELS, LEVERS, derive_baseline
from app.lib.causal_simulator import (
    bridge_sensitivity,
    calibrate,
    causal_report,
    counterfactual,
    scm_structure,
)

router = APIRouter(tags=["因果推演"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CausalRequest(BaseModel):
    """因果推演请求。baseline 可缺省（缺失轴取中性 68），levers 为生活方式杠杆。"""
    baseline: dict[str, float] | None = Field(
        default=None, description="八轴基线分 {A..H: 0-100}；缺省轴取中性 68")
    levers: list[str] = Field(
        default_factory=list, description=f"生活方式杠杆，可选：{sorted(LEVERS)}")
    weeks: int = Field(default=12, ge=1, le=52, description="推演 horizon（周）")
    lever_scale: float = Field(default=1.0, gt=0.0, le=2.0, description="执行强度系数")


# ---------------------------------------------------------------------------
# 输入校验（fail-loud）
# ---------------------------------------------------------------------------

def _validate(req: CausalRequest) -> dict[str, float]:
    bad_axes = [k for k in (req.baseline or {}) if k not in AXES]
    if bad_axes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知轴: {bad_axes}；合法轴为 {AXES}")
    bad_levers = [lv for lv in req.levers if lv not in LEVERS]
    if bad_levers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知杠杆: {bad_levers}；合法杠杆为 {sorted(LEVERS)}")
    for k, v in (req.baseline or {}).items():
        if not (0.0 <= float(v) <= 100.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"轴 {k} 基线分 {v} 越界，须在 0-100")
    # derive_baseline 会补齐缺失轴(中性 68)并 clamp，已通过上面的越界校验
    return derive_baseline(provided=req.baseline)


# ---------------------------------------------------------------------------
# 结构类端点（公开）
# ---------------------------------------------------------------------------

@router.get("/scm", response_model=dict)
async def get_scm():
    """结构因果模型：8 轴节点、有向耦合边、外生杠杆、被承认的未观测混淆。"""
    return scm_structure()


@router.get("/sensitivity", response_model=dict)
async def get_sensitivity():
    """逐耦合边 E-value 敏感性：暴露「耦合网络尚未被因果识别」。"""
    return bridge_sensitivity()


@router.get("/levers", response_model=dict)
async def list_levers():
    """可用生活方式杠杆（含驱动轴与说明）。"""
    return {
        "success": True,
        "levers": [
            {"lever": k, "label": v["label"], "drive": v["drive"], "note": v["note"]}
            for k, v in LEVERS.items()
        ],
        "axes": AXIS_LABELS,
    }


# ---------------------------------------------------------------------------
# 个性化推演端点（需登录）
# ---------------------------------------------------------------------------

@router.post("/counterfactual", response_model=dict)
async def post_counterfactual(
    body: CausalRequest,
    current_user: User = Depends(get_current_user),
):
    """反事实对比：干预轨迹 vs 不干预轨迹，输出逐轴因果贡献估计。"""
    baseline = _validate(body)
    logger.info(f"因果反事实推演 | user_id={current_user.id} | levers={body.levers} | weeks={body.weeks}")
    return counterfactual(baseline, body.levers, body.weeks, body.lever_scale)


@router.post("/calibrate", response_model=dict)
async def post_calibrate(
    body: CausalRequest,
    current_user: User = Depends(get_current_user),
):
    """自助校准：扰动耦合系数(±20%)与执行一致性(0.85-1.0)，输出逐轴 5/95 分位带。"""
    baseline = _validate(body)
    logger.info(f"因果校准推演 | user_id={current_user.id} | levers={body.levers} | weeks={body.weeks}")
    return calibrate(baseline, body.levers, body.weeks, body.lever_scale)


@router.post("/report", response_model=dict)
async def post_report(
    body: CausalRequest,
    current_user: User = Depends(get_current_user),
):
    """因果推演四件套一次性产出（结构 / 反事实 / 校准 / 敏感性）。"""
    baseline = _validate(body)
    logger.info(f"因果推演报告 | user_id={current_user.id} | levers={body.levers} | weeks={body.weeks}")
    return causal_report(baseline, body.levers, body.weeks, body.lever_scale)
