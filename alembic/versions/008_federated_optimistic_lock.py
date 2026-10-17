"""D4 联邦预埋：乐观锁 version_id + 唯一索引 + downgrade 完整往返

Revision ID: 008_federated_optimistic_lock
Revises: 007_add_remaining_models
Create Date: 2026-10-17

背景（10-16 全面评估报告 D4 / S4 联邦学习架构方案）：
    联邦学习场景中，多个成员节点可能并发提交同一 AxisSnapshot / BiomarkerReading。
    无乐观锁时"最后写入胜"导致静默数据丢失；无唯一索引时网络抖动/重试导致
    重复计入，联邦聚合结果被污染。本迁移：

    1. axis_snapshots: 新增 version_id (int, default=1, not null) — 乐观锁
       UniqueConstraint(study_id, date, source) — 同一 study 同一 date 同一 source
         只能一条快照（防止同一渠道重复提交）
    2. biomarker_readings: 新增 version_id (int, default=1, not null) — 乐观锁
       UniqueConstraint(study_id, sampled_at, loinc_code) — 同一 study 同一采样时刻
         同一 Loinc 指标只能一条读数

Downgrade 策略（round-trip 可验证）：
    - 先删约束，再删列
    - downgrade 后再 upgrade 必须无差异（幂等往返）
    - 不 delete table（联邦数据属于生产，任何"降级"都不可删除数据）
"""
from alembic import op
import sqlalchemy as sa


revision = '008_federated_optimistic_lock'
down_revision = '007_add_remaining_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- axis_snapshots: version_id 乐观锁 ---
    op.add_column(
        'axis_snapshots',
        sa.Column('version_id', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_unique_constraint(
        'uq_snapshots_study_date_source',
        'axis_snapshots',
        ['study_id', 'date', 'source'],
    )

    # --- biomarker_readings: version_id 乐观锁 ---
    op.add_column(
        'biomarker_readings',
        sa.Column('version_id', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_unique_constraint(
        'uq_readings_study_ts_loinc',
        'biomarker_readings',
        ['study_id', 'sampled_at', 'loinc_code'],
    )


def downgrade() -> None:
    # 严格反向：先删约束、再删列（顺序反转避免依赖失败）
    op.drop_constraint(
        'uq_readings_study_ts_loinc',
        'biomarker_readings',
        type_='unique',
    )
    op.drop_column('biomarker_readings', 'version_id')

    op.drop_constraint(
        'uq_snapshots_study_date_source',
        'axis_snapshots',
        type_='unique',
    )
    op.drop_column('axis_snapshots', 'version_id')
