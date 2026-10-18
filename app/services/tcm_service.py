"""中医辨证论治服务"""
import json
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tcm_profile import TcmProfile
from app.models.tcm_syndrome import TcmSyndromeDiagnosis
from app.models.tcm_formula import TcmFormulaRecommendation
from app.core.tcm_engine import TcmDiagnosisEngine


engine = TcmDiagnosisEngine()


async def analyze_constitution(db: AsyncSession, user_id: str, questionnaire_data: dict) -> dict:
    """体质辨识 - 调用引擎计算体质类型和评分"""
    from app.core.tcm_engine import CONSTITUTION_DIMENSIONS

    result = engine.analyze_constitution(questionnaire_data)

    # 更新数据库中的体质档案
    profile_result = await db.execute(
        select(TcmProfile).where(TcmProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    if profile:
        # 获取主要体质的中文名称
        dim = CONSTITUTION_DIMENSIONS.get(result.primary_type, {})
        primary_name = dim.get("name", result.primary_type)
        profile.constitution_type = primary_name
        profile.constitution_score = result.scores
        await db.commit()
        await db.refresh(profile)

    logger.info(f"Constitution analysis for user {user_id}: primary={result.primary_type}")

    return {
        "status": "completed",
        "primary_type": result.primary_type,
        "scores": result.scores,
        "description": result.description,
        "all_types": result.all_types,
    }


async def diagnose_syndrome(db: AsyncSession, user_id: str, symptoms: list[str], **kwargs) -> dict:
    """AI 辨证"""
    constitution = kwargs.get("constitution")
    tongue_analysis = kwargs.get("tongue_analysis")
    pulse = kwargs.get("pulse_description")

    syndrome = await engine.diagnose_syndrome(
        symptoms=symptoms,
        tongue_analysis=tongue_analysis,
        pulse_description=pulse,
        constitution=constitution,
    )

    logger.info(f"TCM diagnosis for user {user_id}: {syndrome['syndrome_name']}")
    return {
        "status": "completed",
        "syndrome": syndrome,
    }


async def create_delivery_order(db: AsyncSession, user_id: str, formula_id: str, address: str) -> dict:
    """创建中药配送订单"""
    # 检查方剂推荐存在
    result = await db.execute(
        select(TcmFormulaRecommendation).where(
            TcmFormulaRecommendation.id == formula_id,
        )
    )
    formula = result.scalar_one_or_none()
    if not formula:
        return {"status": "error", "message": "Formula recommendation not found"}

    from app.models.tcm_formula import TcmDeliveryOrder
    import uuid
    from datetime import datetime, timezone

    order = TcmDeliveryOrder(
        id=str(uuid.uuid4()),
        user_id=user_id,
        formula_id=formula_id,
        pharmacy_name="一方制药(模拟)",
        order_status="pending",
        delivery_address=address,
        total_fee=None,  # 待药房确认
        ordered_at=datetime.now(timezone.utc),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    logger.info(f"Delivery order created: {order.id} for user {user_id}")
    return {
        "status": "completed",
        "order_id": str(order.id),
        "pharmacy_name": order.pharmacy_name,
        "order_status": order.order_status,
    }
