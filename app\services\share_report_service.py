"""可分享健康报告服务 - 生成分享链接、社交卡片"""
import uuid
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.share_report import SharedReport
from app.models.user import User


async def generate_share_token() -> str:
    """生成32位随机分享令牌"""
    return secrets.token_urlsafe(24)[:32]


async def create_shared_report(
    db: AsyncSession,
    user_id: str,
    report_type: str,
    title: str,
    report_data: dict,
    summary_text: str = "",
    health_score: int | None = None,
    risk_level: str | None = None,
    expires_days: int | None = 30,
) -> SharedReport:
    """创建可分享的健康报告

    Args:
        user_id: 用户ID
        report_type: 报告类型
        title: 报告标题
        report_data: 报告数据快照
        summary_text: 摘要文本
        health_score: 健康评分(0-100)
        risk_level: 风险等级
        expires_days: 有效期天数，None表示永不过期
    """
    # 生成唯一分享令牌
    for _ in range(10):
        token = await generate_share_token()
        existing = await db.execute(
            select(SharedReport).where(SharedReport.share_token == token)
        )
        if not existing.scalar_one_or_none():
            break
    else:
        raise ValueError("Failed to generate unique share token")

    # 计算有效期
    expires_at = None
    if expires_days:
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

    # 生成社交卡片元数据
    og_title = f"{title} | HealthLens 健康报告"
    og_description = summary_text[:200] if summary_text else "基于你的独特生物学特征的健康改善量化追踪"
    if health_score is not None:
        og_description = f"健康评分: {health_score}/100 | {og_description}"

    report = SharedReport(
        id=str(uuid.uuid4()),
        share_token=token,
        user_id=user_id,
        report_type=report_type,
        title=title,
        summary_text=summary_text,
        report_data=report_data,
        is_public=True,
        view_count=0,
        share_count=0,
        expires_at=expires_at,
        og_title=og_title,
        og_description=og_description,
        health_score=health_score,
        risk_level=risk_level,
    )

    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info(f"[SharedReport] Created: user={user_id}, token={token}, type={report_type}")
    return report


async def get_shared_report(
    db: AsyncSession,
    share_token: str,
    increment_view: bool = True,
) -> SharedReport | None:
    """获取分享报告（公开访问）

    Args:
        share_token: 分享令牌
        increment_view: 是否增加查看计数
    """
    result = await db.execute(
        select(SharedReport).where(SharedReport.share_token == share_token)
    )
    report = result.scalar_one_or_none()

    if not report:
        return None

    # 检查是否公开
    if not report.is_public:
        return None

    # 检查是否过期
    if report.expires_at and report.expires_at < datetime.utcnow():
        return None

    # 增加查看计数
    if increment_view:
        report.view_count += 1
        await db.commit()

    return report


async def get_user_shared_reports(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SharedReport], int]:
    """获取用户的所有分享报告"""
    query = select(SharedReport).where(SharedReport.user_id == user_id).order_by(
        SharedReport.created_at.desc()
    )

    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    # 分页
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    reports = result.scalars().all()

    return list(reports), total


async def revoke_shared_report(
    db: AsyncSession,
    report_id: str,
    user_id: str,
) -> bool:
    """撤销分享报告（设为不公开）"""
    result = await db.execute(
        select(SharedReport).where(
            SharedReport.id == report_id,
            SharedReport.user_id == user_id,
        )
    )
    report = result.scalar_one_or_none()

    if not report:
        return False

    report.is_public = False
    await db.commit()

    logger.info(f"[SharedReport] Revoked: id={report_id}, user={user_id}")
    return True


async def increment_share_count(
    db: AsyncSession,
    share_token: str,
) -> None:
    """增加分享次数"""
    result = await db.execute(
        select(SharedReport).where(SharedReport.share_token == share_token)
    )
    report = result.scalar_one_or_none()

    if report:
        report.share_count += 1
        await db.commit()


async def get_report_owner(
    db: AsyncSession,
    share_token: str,
) -> User | None:
    """获取分享报告的所有者"""
    result = await db.execute(
        select(SharedReport).where(SharedReport.share_token == share_token)
    )
    report = result.scalar_one_or_none()

    if not report:
        return None

    result = await db.execute(
        select(User).where(User.id == report.user_id)
    )
    return result.scalar_one_or_none()
