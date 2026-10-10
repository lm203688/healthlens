"""睡眠数据模型 - 支持睡眠修复支柱"""
from datetime import datetime, date
from sqlalchemy import String, Float, Integer, ForeignKey, Date, Boolean, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, UUIDPrimaryKeyMixin, TimestampMixin


class SleepRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """单次睡眠记录"""
    __tablename__ = "sleep_records"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    sleep_date: Mapped[date] = mapped_column(Date, index=True)

    # 时间参数
    bedtime: Mapped[str | None] = mapped_column(String(5))  # "23:30"
    wake_time: Mapped[str | None] = mapped_column(String(5))  # "07:00"
    sleep_latency_min: Mapped[int | None] = mapped_column(Integer)  # 入睡潜伏期(分钟)
    total_duration_min: Mapped[int | None] = mapped_column(Integer)  # 总时长(分钟)

    # 睡眠阶段
    deep_sleep_min: Mapped[float | None] = mapped_column(Float)  # 深睡时长
    light_sleep_min: Mapped[float | None] = mapped_column(Float)  # 浅睡时长
    rem_sleep_min: Mapped[float | None] = mapped_column(Float)  # REM时长
    awake_min: Mapped[float | None] = mapped_column(Float)  # 觉醒时长

    # 质量指标
    sleep_efficiency: Mapped[float | None] = mapped_column(Float)  # 入睡效率 %
    awakenings_count: Mapped[int | None] = mapped_column(Integer)  # 觉醒次数
    hrv_avg: Mapped[float | None] = mapped_column(Float)  # 平均HRV
    hrv_recovery: Mapped[float | None] = mapped_column(Float)  # HRV恢复率

    # 环境与主观
    room_temp: Mapped[float | None] = mapped_column(Float)  # 室温
    subjective_score: Mapped[int | None] = mapped_column(Integer)  # 主观评分1-10
    sleep_notes: Mapped[str | None] = mapped_column(Text)

    # 数据来源
    source: Mapped[str | None] = mapped_column(String(50))  # wearable/manual/import
    raw_data: Mapped[dict | None] = mapped_column(JSON)  # 原始设备数据

    # 综合评分（0-100）
    sleep_score: Mapped[float | None] = mapped_column(Float, index=True)


class SleepChecklist(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """睡前准备清单记录"""
    __tablename__ = "sleep_checklists"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    checklist_date: Mapped[date] = mapped_column(Date, index=True)
    warm_bath: Mapped[bool | None] = mapped_column(Boolean, default=False)
    blue_light_off: Mapped[bool | None] = mapped_column(Boolean, default=False)
    room_temp_ok: Mapped[bool | None] = mapped_column(Boolean, default=False)
    herbal_drink: Mapped[bool | None] = mapped_column(Boolean, default=False)
    meditation_done: Mapped[bool | None] = mapped_column(Boolean, default=False)
    all_completed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    completion_time: Mapped[datetime | None] = mapped_column()


class RepairScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """细胞修复综合评分"""
    __tablename__ = "repair_scores"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    score_date: Mapped[date] = mapped_column(Date, index=True)

    # 综合修复评分 (0-100)
    total_score: Mapped[float | None] = mapped_column(Float, index=True)
    repair_age: Mapped[float | None] = mapped_column(Float)  # 修复年龄
    calendar_age: Mapped[int | None] = mapped_column(Integer)  # 日历年龄
    percentile: Mapped[float | None] = mapped_column(Float)  # 同龄百分位

    # 七大维度评分
    deep_sleep_score: Mapped[float | None] = mapped_column(Float)  # 深度睡眠 25%
    hrv_recovery_score: Mapped[float | None] = mapped_column(Float)  # HRV恢复 20%
    inflammation_score: Mapped[float | None] = mapped_column(Float)  # 炎症水平 15%
    exercise_adherence_score: Mapped[float | None] = mapped_column(Float)  # 运动依从 15%
    nutrition_score: Mapped[float | None] = mapped_column(Float)  # 营养质量 10%
    circadian_score: Mapped[float | None] = mapped_column(Float)  # 昼夜节律 10%
    subjective_energy_score: Mapped[float | None] = mapped_column(Float)  # 主观精力 5%

    # 权重配置（可个性化调整）
    weights: Mapped[dict | None] = mapped_column(JSON)

    # 计算快照
    input_snapshot: Mapped[dict | None] = mapped_column(JSON)
    damage_analysis: Mapped[dict | None] = mapped_column(JSON)  # 细胞损伤分析

    # 数据来源
    sources: Mapped[dict | None] = mapped_column(JSON)  # {"sleep": true, "wearable": true, "lab": false, "survey": true}
