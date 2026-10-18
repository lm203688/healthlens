"""健康目标模型 - 用户健康目标设定与追踪"""
from datetime import datetime
from sqlalchemy import String, Numeric, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin
import uuid


class HealthGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """健康目标"""
    __tablename__ = "health_goals"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    goal_type: Mapped[str] = mapped_column(String(50))  # weight / steps / bp / glucose / exercise / sleep
    goal_name: Mapped[str] = mapped_column(String(200))
    target_value: Mapped[float] = mapped_column(Numeric(10, 2))
    current_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[datetime] = mapped_column(DateTime)
    target_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / completed / abandoned
    progress: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0)  # 0-100
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class GoalProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """目标进度记录"""
    __tablename__ = "goal_progress"

    goal_id: Mapped[str] = mapped_column(String(36), ForeignKey("health_goals.id"), index=True)
    value: Mapped[float] = mapped_column(Numeric(10, 2))
    recorded_at: Mapped[datetime] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
