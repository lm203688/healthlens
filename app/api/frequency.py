"""放松音频体验 API — 小程序对接端点（原「频率疗法」）

S3-4（2026-10-13）合规降级：本端点仅提供放松 / 睡眠音频推荐，not_clinical，
不进入八轴机制链、不宣称任何疗效。字段名（prescription 等）保留以兼容前端。

R3（2026-10-20）fail-closed 落地：所有 GET/POST 出口都过 claims_engine.filter_output，
任一 banned_terms 命中即返回 403，不再依赖 disclaimer 或人肉守。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from loguru import logger

from app.models.user import User
from app.api.deps import get_current_user
from app.lib.claims_engine import filter_output, ClaimsPolicyError, get_user_jurisdiction
from app.services.frequency_prescription import (
    FrequencyPrescriptionEngine,
    get_prescription,
    get_prescriptions_by_user,
    store_prescription,
)

router = APIRouter(tags=["放松音频"])


def _apply_claims(payload: dict, user: User, endpoint: str) -> dict:
    """按用户法域过滤输出，fail-closed：任一 banned_term 命中即 403。"""
    try:
        result = filter_output(payload, get_user_jurisdiction(user), endpoint=endpoint)
        if result.violations or result.removed_fields:
            logger.warning(
                f"[Claims] frequency endpoint={endpoint} user={user.id} "
                f"violations={len(result.violations)} removed={len(result.removed_fields)}"
            )
        return result.payload
    except ClaimsPolicyError as e:
        logger.warning(f"[Claims] BLOCKED endpoint={endpoint} user={user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Claims policy violation: {str(e)}",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrescriptionRequest(BaseModel):
    """基于诊断生成频率处方请求"""
    diagnosis_data: dict = Field(..., description="五层诊断数据（fusion chain 格式）")
    tcm_symptoms: list[str] = Field(default_factory=list, description="额外中医症状")


class PrescriptionFeedback(BaseModel):
    """处方反馈"""
    track_id: str = Field(..., description="曲目ID")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    felt_better: bool | None = Field(None, description="是否感觉改善")
    notes: str = Field("", description="备注")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/tracks")
async def list_tracks(
    current_user: User = Depends(get_current_user),
):
    """获取所有可用频率曲目列表（供小程序同步）"""
    from app.services.frequency_prescription import TRACKS

    tracks = []
    for t in TRACKS:
        tracks.append({
            "track_id": t["id"],
            "title": t["title"],
            "subtitle": t["subtitle"],
            "frequency": t["frequency"],
            "beatFreq": t["beatFreq"],
            "category": t["category"],
            "description": t["description"],
            "duration": t["duration"],
            "audioSrc": t["audioSrc"],
            "symptoms": t["symptoms"],
            "bodyParts": t["bodyParts"],
        })

    response = {
        "success": True,
        "count": len(tracks),
        "tracks": tracks,
    }
    return _apply_claims(response, current_user, "/api/v1/frequency/tracks")


@router.post("/prescription", status_code=status.HTTP_201_CREATED)
async def create_prescription(
    body: PrescriptionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    基于五层诊断生成个性化频率处方。

    - 输入：五层诊断数据（含 layer3_pathways, layer4_syndromes）
    - 输出：个性化频率处方（含曲目、日程、预期效果、禁忌）
    """
    engine = FrequencyPrescriptionEngine()
    prescription = engine.generate_prescription(
        user_id=current_user.id,
        diagnosis_data=body.diagnosis_data,
        tcm_symptoms=body.tcm_symptoms,
    )

    store_prescription(prescription)

    logger.info(f"频率处方已创建 | prescription_id={prescription['prescription_id']} | user_id={current_user.id}")

    response = {
        "success": True,
        "prescription_id": prescription["prescription_id"],
        "prescription": prescription,
    }
    return _apply_claims(response, current_user, "/api/v1/frequency/prescription")


@router.get("/prescription/{prescription_id}")
async def get_prescription_detail(
    prescription_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取频率处方详情"""
    prescription = get_prescription(prescription_id)
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"处方 {prescription_id} 不存在",
        )

    if prescription.get("user_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该处方",
        )

    response = {
        "success": True,
        "prescription": prescription,
    }
    return _apply_claims(response, current_user, "/api/v1/frequency/prescription")


@router.get("/prescriptions")
async def list_user_prescriptions(
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的所有频率处方"""
    prescriptions = get_prescriptions_by_user(current_user.id)
    response = {
        "success": True,
        "count": len(prescriptions),
        "prescriptions": prescriptions,
    }
    return _apply_claims(response, current_user, "/api/v1/frequency/prescriptions")


@router.post("/prescription/{prescription_id}/feedback")
async def submit_feedback(
    prescription_id: str,
    body: PrescriptionFeedback,
    current_user: User = Depends(get_current_user),
):
    """提交频率处方使用反馈"""
    prescription = get_prescription(prescription_id)
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"处方 {prescription_id} 不存在",
        )

    if prescription.get("user_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该处方",
        )

    feedback_entry = {
        "track_id": body.track_id,
        "rating": body.rating,
        "felt_better": body.felt_better,
        "notes": body.notes,
    }

    if "feedback" not in prescription:
        prescription["feedback"] = []
    prescription["feedback"].append(feedback_entry)

    logger.info(f"频率处方反馈已记录 | prescription_id={prescription_id} | track_id={body.track_id} | rating={body.rating}")

    return {
        "success": True,
        "message": "反馈已记录",
    }


@router.post("/prescription/from-diagnosis-agent")
async def create_prescription_from_diagnosis(
    diagnosis_agent_task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    从 AI 诊断 Agent 的结果直接生成频率处方。

    - 输入：AI 诊断任务的 task_id
    - 自动查询诊断结果并生成对应频率处方
    """
    from app.api.v1.diagnosis_agent import _task_store

    task = _task_store.get(diagnosis_agent_task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"诊断任务 {diagnosis_agent_task_id} 不存在",
        )

    if task.get("user_id") != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该诊断任务",
        )

    if task.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"诊断任务尚未完成，当前状态: {task.get('status')}",
        )

    diagnosis_data = task.get("result", {})
    if not diagnosis_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="诊断任务结果为空",
        )

    engine = FrequencyPrescriptionEngine()
    prescription = engine.generate_prescription(
        user_id=current_user.id,
        diagnosis_data=diagnosis_data,
    )

    store_prescription(prescription)

    logger.info(
        f"从诊断Agent生成频率处方 | task_id={diagnosis_agent_task_id} | "
        f"prescription_id={prescription['prescription_id']}"
    )

    response = {
        "success": True,
        "prescription_id": prescription["prescription_id"],
        "prescription": prescription,
    }
    return _apply_claims(response, current_user, "/api/v1/frequency/prescription/from-diagnosis-agent")
