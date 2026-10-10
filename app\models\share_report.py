"""可分享健康报告模型 - 社交分享卡片"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, DateTime, Text, JSON, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class SharedReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """可分享的健康报告
    用户生成健康报告后，可以创建一个公开分享链接
    访问者无需登录即可查看报告摘要
    """
    __tablename__ = "shared_reports"

    share_token: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )  # 公开访问令牌

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )  # 报告所属用户

    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="health_summary"
    )  # 报告类型: health_summary / tcm / genome / risk

    title: Mapped[str] = mapped_column(String(200), nullable=False)  # 报告标题

    summary_text: Mapped[str] = mapped_column(Text)  # 报告摘要文本

    # 报告数据快照（JSON格式，避免后续数据变化影响分享内容）
    report_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    # 公开分享设置
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1"
    )  # 是否公开可访问

    view_count: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 查看次数

    share_count: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 分享次数

    # 有效期
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, index=True
    )  # 过期时间，NULL表示永不过期

    # 社交卡片元数据
    og_title: Mapped[str | None] = mapped_column(String(200))
    og_description: Mapped[str | None] = mapped_column(String(500))
    og_image_url: Mapped[str | None] = mapped_column(String(1000))

    # 报告健康评分（0-100），用于社交卡片展示
    health_score: Mapped[int | None] = mapped_column(Integer)

    # 风险等级: low / medium / high
    risk_level: Mapped[str | None] = mapped_column(String(20))

    extra_data: Mapped[dict | None] = mapped_column(JSON)  # 扩展数据
