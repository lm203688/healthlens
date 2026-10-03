"""可分享健康报告 API - 生成分享链接、管理分享报告"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.share_report_service import (
    create_shared_report,
    get_user_shared_reports,
    revoke_shared_report,
)
from app.services.analysis_service import analyze_user_observations
from app.models.health_record import HealthProfile
from app.models.diagnosis import DiagnosisResult
from app.models.observation import HealthObservation
from sqlalchemy import select, func

router = APIRouter(tags=["分享报告"])


@router.post("/share")
async def share_health_report(
    report_type: str = Query("health_summary", description="报告类型: health_summary"),
    expires_days: int = Query(30, description="有效期天数，0表示永不过期"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成健康报告的公开分享链接

    创建报告快照，生成唯一分享令牌。
    访问者无需登录即可查看报告摘要。
    """
    # 获取健康档案
    profile_result = await db.execute(
        select(HealthProfile).where(HealthProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    profile_data = None
    if profile:
        profile_data = {
            "name": profile.name or current_user.nickname or "健康用户",
            "gender": profile.gender,
            "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
            "blood_type": profile.blood_type,
            "height_cm": float(profile.height_cm) if profile.height_cm else None,
            "weight_kg": float(profile.weight_kg) if profile.weight_kg else None,
        }

    # 获取健康分析
    analysis = await analyze_user_observations(db, str(current_user.id))

    # 获取活跃诊断
    diag_result = await db.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.user_id == current_user.id,
            DiagnosisResult.status == "confirmed",
        )
    )
    diagnoses = diag_result.scalars().all()
    diagnosis_list = [
        {"id": str(d.id), "text": d.diagnosis_text, "icd": d.icd_code}
        for d in diagnoses
    ]

    # 计算健康评分
    health_score = _calculate_health_score(analysis)

    # 风险等级
    risk_level = "low"
    abnormal_count = analysis.get("abnormal_count", 0)
    if abnormal_count >= 5:
        risk_level = "high"
    elif abnormal_count >= 2:
        risk_level = "medium"

    # 生成报告摘要
    nickname = current_user.nickname or "健康用户"
    title = f"{nickname}的健康报告"
    summary_items = []
    if health_score is not None:
        summary_items.append(f"健康评分 {health_score}/100")
    if abnormal_count > 0:
        summary_items.append(f"{abnormal_count}项指标异常")
    summary_text = " | ".join(summary_items) if summary_items else "暂无健康数据"

    # 报告数据快照（只分享摘要，不分享详细隐私数据）
    report_data = {
        "report_type": report_type,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "health_score": health_score,
        "risk_level": risk_level,
        "profile": {
            "gender": profile_data.get("gender") if profile_data else None,
            "blood_type": profile_data.get("blood_type") if profile_data else None,
        },
        "analysis_summary": {
            "total_items": analysis.get("total_items", 0),
            "abnormal_count": abnormal_count,
            "risk_factors": analysis.get("risk_factors", [])[:5],
            "recommendations": analysis.get("recommendations", [])[:3],
        },
        "active_diagnoses": diagnosis_list,
        "nickname": nickname,
    }

    # 创建分享报告
    shared_report = await create_shared_report(
        db,
        user_id=str(current_user.id),
        report_type=report_type,
        title=title,
        report_data=report_data,
        summary_text=summary_text,
        health_score=health_score,
        risk_level=risk_level,
        expires_days=expires_days if expires_days > 0 else None,
    )

    # 分享链接
    share_url = f"/share/report/{shared_report.share_token}"

    return {
        "success": True,
        "data": {
            "share_token": shared_report.share_token,
            "share_url": share_url,
            "title": shared_report.title,
            "health_score": shared_report.health_score,
            "risk_level": shared_report.risk_level,
            "expires_at": shared_report.expires_at.isoformat() if shared_report.expires_at else None,
            "view_count": shared_report.view_count,
            "share_count": shared_report.share_count,
            "og_title": shared_report.og_title,
            "og_description": shared_report.og_description,
        },
        "message": "分享链接已生成，有效期30天",
    }


@router.get("/my-shares")
async def get_my_shared_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取我创建的所有分享报告"""
    reports, total = await get_user_shared_reports(
        db, str(current_user.id), page, page_size
    )

    data = [
        {
            "id": str(r.id),
            "share_token": r.share_token,
            "share_url": f"/share/report/{r.share_token}",
            "report_type": r.report_type,
            "title": r.title,
            "health_score": r.health_score,
            "risk_level": r.risk_level,
            "is_public": r.is_public,
            "view_count": r.view_count,
            "share_count": r.share_count,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]

    return {
        "success": True,
        "data": {
            "items": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/{report_id}/revoke")
async def revoke_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """撤销/取消分享报告"""
    success = await revoke_shared_report(db, report_id, str(current_user.id))
    if not success:
        raise HTTPException(status_code=404, detail="报告不存在或无权限")

    return {
        "success": True,
        "message": "报告已撤销，分享链接失效",
    }


def _calculate_health_score(analysis: dict) -> int:
    """根据分析结果计算健康评分（0-100）"""
    total = analysis.get("total_items", 0)
    abnormal = analysis.get("abnormal_count", 0)

    if total == 0:
        return None  # 无数据时不评分

    # 基础分：100 - 异常项比例 * 50
    base_score = 100 - (abnormal / total) * 50

    # 风险因素扣分
    risk_factors = analysis.get("risk_factors", [])
    risk_penalty = len(risk_factors) * 3

    score = max(0, min(100, int(base_score - risk_penalty)))
    return score
