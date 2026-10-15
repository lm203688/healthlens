"""n-of-1 纵向追踪数据模型（S2-2）

设计原则：
- 「数据底座先行」：先建模型 + API 骨架，让真实纵向数据一接入就有落点；
  避免重蹈"骨架未接线"的坑——每个字段都有明确语义，API 端点可被外部
  穿戴设备/化验单/干预记录直接写入
- 「可审计」：每次八轴快照保留输入指纹（sha256）与法域，允许任意时间点
  追溯「当时用了什么数据、按哪个法域输出」
- 「干预对齐」：InterventionEvent 记录每一次干预的开始/结束，与 AxisSnapshot
  的时间戳对齐，即可计算"干预前后 vs 反事实"的差值——这是因果推断装置的
  数据源
- 「区域数据驻留」：Study.region 与 User.jurisdiction 一致，跨区查询
  通过 region_guard 拦截（S3 阶段联邦学习的基础）

表结构：
    LongitudinalStudy    一项纵向研究（一个用户可有多项）
    AxisSnapshot         日粒度的八轴打分快照（TimescaleDB 兼容）
    InterventionEvent    干预事件（饮食/药物/生活方式变更）
    BiomarkerReading     关键化验单读数（HbA1c/glucose/CRP/…）
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LongitudinalStudy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """一项 n-of-1 纵向研究。

    对应报告 §S2-2「n-of-1 自追踪（8-12 周）」：一个用户 + 一台穿戴设备
    + 定期化验单 + 干预记录 → 八轴轨迹 vs 干预时间线。

    字段约定：
    - cohort: n-of-1 / n-of-k / cohort 三种研究规模的枚举
    - data_residency_region: 数据驻留区域（CN/US/EU/UK/AU），
      必须与 user.jurisdiction 一致（S3 联邦学习的分区键）
    - status: recruiting / active / paused / completed / terminated
    - baseline_snapshot_id: 基线快照 ID，用于计算相对基线的轨迹偏移
    """

    __tablename__ = "longitudinal_studies"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cohort: Mapped[str] = mapped_column(
        String(20), default="n_of_1"
    )  # n_of_1 / n_of_k / cohort
    status: Mapped[str] = mapped_column(
        String(20), default="recruiting"
    )  # recruiting / active / paused / completed / terminated
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    data_residency_region: Mapped[str] = mapped_column(
        String(10), default="CN"
    )  # CN / US / EU / UK / AU
    baseline_snapshot_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    protocol: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # 研究方案（干预类型、随访频率、终点指标等）
    consent_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 研究知情同意书版本
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_studies_user_status", "user_id", "status"),
        Index("ix_studies_region", "data_residency_region"),
    )


class AxisSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """日粒度的八轴打分快照。

    一行 = 一个用户在某一天的八轴完整打分。存储：
    - axis_scores: {axis_id: {score, measured, penalty_ratio}} 紧凑 JSON
    - input_fingerprint: 输入数据的 sha256 摘要，用于审计追溯
    - jurisdiction: 打分时的法域（因为阈值会按法域变化，A2 参数外置）
    - source: manual / wearable_sync / biomarker_import / composite
    """

    __tablename__ = "axis_snapshots"

    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("longitudinal_studies.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    jurisdiction: Mapped[str] = mapped_column(
        String(10), default="cn", nullable=False
    )
    axis_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weak_axes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    input_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # sha256 of inputs
    input_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(
        String(30), default="manual", nullable=False
    )  # manual / wearable_sync / biomarker_import / composite
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_snapshots_study_date", "study_id", "date"),
        Index("ix_snapshots_user_date", "user_id", "date"),
    )


class InterventionEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """干预事件（S2-2 因果推断装置的核心数据源）。

    对应因果引擎 `app/lib/causal_simulator.py` 的干预变量声明：
    - intervention_type: 干预类型枚举（饮食/药物/生活方式/行为）
    - target_axis: 目标八轴（可选，null 表示全局干预）
    - intensity: 强度（0-1，用于敏感性分析）
    - started_at / ended_at: 时间戳，与 AxisSnapshot.date 对齐后可
      计算「干预前 k 天 vs 干预期 vs 干预后 k 天」的对比窗口
    """

    __tablename__ = "intervention_events"

    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("longitudinal_studies.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    intervention_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_axis: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )  # A-H 或 null（全局干预）
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intensity: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    intervention_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # 具体方案（药食同源配方/剂量/频次等）；避开 SQLAlchemy 保留字 metadata

    __table_args__ = (
        Index("ix_interventions_study_time", "study_id", "started_at"),
        Index("ix_interventions_type", "intervention_type"),
    )


class BiomarkerReading(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """关键化验单读数（HbA1c/glucose/CRP/ALT/…）。

    与 HealthObservation 的区别：本表专门承载纵向研究的基线/随访化验，
    便于按 study_id 聚合，避免从通用观察表里筛选。
    """

    __tablename__ = "biomarker_readings"

    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("longitudinal_studies.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True, nullable=False
    )
    loinc_code: Mapped[str] = mapped_column(String(50), nullable=False)
    loinc_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(15, 5), nullable=True)
    value_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lab_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_low: Mapped[Decimal | None] = mapped_column(Numeric(15, 5), nullable=True)
    reference_high: Mapped[Decimal | None] = mapped_column(Numeric(15, 5), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_readings_study_time", "study_id", "sampled_at"),
        Index("ix_readings_loinc", "loinc_code"),
    )
