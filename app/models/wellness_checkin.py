"""用户自测闭环（SIIV 的 V 端）— wellness 健康自评，非医疗评估

用户每周自测 3 个 wellness 维度（能量 / 消化 / 睡眠），回填个人画像备注，
形成「输入 → 个性化 → 行动 → 自测反馈」的数据飞轮。
评分 1-5（1=很差，5=很好），属于主观健康感受记录，不构成诊断。
"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class WellnessCheckin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """用户 wellness 自测记录"""

    __tablename__ = "wellness_checkins"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    # 三个 wellness 维度自评分（1-5）
    energy_score: Mapped[int] = mapped_column(Integer)        # 精力/活力
    digestion_score: Mapped[int] = mapped_column(Integer)     # 消化/肠胃舒适
    sleep_score: Mapped[int] = mapped_column(Integer)         # 睡眠/休息质量
    # 可选：当日主观备注（如「今天散步 30 分钟」「晚睡」）
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 自测日期（可回溯补填，默认创建时间）
    checkin_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
