"""运行时审计事件表（简化版 wellness 安全护栏）

仅记录 4 类轻量异常信号，用于事后巡检与风险评分可视化：
  1. sensitive_info_leak  — 输出文本疑似泄露手机号/邮箱/身份证
  2. out_of_bounds_evidence — 个性化推荐出现越界证据等级（如 L4）
  3. input_anomaly        — 用户输入异常（超长 / 控制字符）
  4. output_anomaly       — 输出异常（超长 / 重复模式，疑似失控生成）

非日志系统、非入侵检测；纯 wellness 平台的轻量自检。
"""
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """一次审计命中事件"""

    __tablename__ = "audit_events"

    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(80), index=True)   # 触发端点
    event_type: Mapped[str] = mapped_column(String(40), index=True)  # 上述 4 类之一
    severity: Mapped[int] = mapped_column(Integer, default=1)        # 1=低 2=中 3=高
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # 命中说明（已脱敏）
