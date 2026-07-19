from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HealthRecord(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "health_records"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))       # 本地存储路径
    file_size: Mapped[int] = mapped_column(default=0)
    content_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded/parsing/completed/failed
    parse_result: Mapped[str | None] = mapped_column(Text, nullable=True)  # 解析结果JSON
    observations_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
