"""脉象解读 API（agent 可调用的「号脉判断」入口）

两个端点：
- POST /api/v1/agent/pulse   ：传 user_ref（号脉设备上报身份），拉取最近 hl.pulse.* 特征并解读
- POST /api/v1/pulse/interpret：直接传一组成熟特征（硬件/测试直连），即时解读

均返回脉象标签 + 八轴信号 + 养生参考 + 健康护栏。非医疗定位。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.lib import pulse_engine

router = APIRouter(prefix="/api/v1", tags=["脉象解读"])


class PulseInterpretIn(BaseModel):
    features: dict[str, Any] = Field(..., description="hl.pulse.* 特征键值")
    user_ref: str | None = Field(default=None, description="可选，仅用于回显")


class PulseByUserIn(BaseModel):
    user_ref: str = Field(..., description="号脉设备上报时使用的 user_ref")
    days: int = Field(default=7, ge=1, le=60)


@router.post("/pulse/interpret")
def interpret_pulse(req: PulseInterpretIn):
    if not req.features:
        raise HTTPException(status_code=400, detail="features 不能为空")
    try:
        result = pulse_engine.classify_pulse(req.features)
    except pulse_engine.PulseKnowledgeBaseError as exc:
        # 知识库不可用：明确 503，绝不用空库产出一个「看起来正常」的假解读
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    result["user_ref"] = req.user_ref
    return result


@router.post("/agent/pulse")
def agent_pulse(req: PulseByUserIn):
    """供 agent / 前端按 user_ref 拉取并解读最近号脉结果。"""
    try:
        from app.api.device_metrics import recent
        from app.connectors.pulse_gateway import interpret_payloads
    except Exception as exc:  # 模块未加载
        raise HTTPException(status_code=503, detail=f"脉象服务不可用: {exc}")

    payloads = recent(req.user_ref, req.days)
    out = interpret_payloads(payloads, req.user_ref)
    if not out["available"]:
        return {
            "available": False,
            "user_ref": req.user_ref,
            "pulse_interpretation": None,
            "message": "暂无该 user_ref 的号脉上报数据",
        }
    return {
        "available": True,
        "user_ref": req.user_ref,
        "pulse_interpretation": out["pulse_interpretation"],
        "items": out["items"],
    }
