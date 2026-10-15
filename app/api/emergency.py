"""健康护栏预检端点

独立于中间件的「显式预检」接口：前端在提交自由文本前调用，
若命中紧急信号则立即渲染强提示，不再发起后续业务请求。

设计要点：
- 无认证要求（护栏不应因未登录而失效——未登录用户同样可能处于紧急情况）
- 纯只读，不产生任何副作用
- 与中间件共用同一份 `check_emergency`，保证判定逻辑唯一
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.emergency_interceptor import check_emergency

router = APIRouter(tags=["健康护栏"])


class EmergencyCheckRequest(BaseModel):
    """预检请求"""
    text: str = Field(..., min_length=0, max_length=2000, description="用户自由文本输入")


class EmergencySignalOut(BaseModel):
    """信号输出"""
    category: str
    keywords: list[str]
    urgency: str = "immediate"


class EmergencyCheckResponse(BaseModel):
    """预检响应"""
    success: bool = True
    is_emergency: bool = False
    signal: EmergencySignalOut | None = None
    guidance: str | None = None
    message: str | None = None
    code: str | None = None


@router.post("/check")
async def check_emergency_endpoint(req: EmergencyCheckRequest) -> EmergencyCheckResponse:
    """文本健康护栏预检

    前端应在用户提交症状/健康描述前调用此端点：
    - `is_emergency=true` → 渲染 `guidance` 强提示，终止后续请求
    - `is_emergency=false` → 正常发起业务请求
    """
    result = check_emergency(req.text or "")
    if not result.is_emergency:
        return EmergencyCheckResponse(success=True, is_emergency=False)

    return EmergencyCheckResponse(
        success=True,
        is_emergency=True,
        signal=EmergencySignalOut(
            category=result.signal.category,
            keywords=result.signal.keywords,
            urgency=result.signal.urgency,
        )
        if result.signal
        else None,
        guidance=result.guidance,
        message=result.message,
        code="emergency_signal_detected",
    )
