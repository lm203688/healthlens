"""D4 联邦预埋：乐观锁 version_id + 唯一索引 + downgrade 完整往返

Revision ID: 008_federated_optimistic_lock
Revises: 007_add_remaining_models
Create Date: 2026-10-17

背景（10-16 全面评估报告 D4 / S4 联邦学习架构方案）：
    联邦学习场景中，多个成员节点可能并发提交同一 AxisSnapshot / BiomarkerReading。
    无乐观锁时"最后写入胜"导致静默数据丢失；无唯一索引时网络抖动/重试导致
    重复计入，联邦聚合结果被污染。本迁移：

    1. axis_snapshots: 新增 version_id (int, default=1, not null) — 乐观锁
       唯一索引 uq_snapshots_study_date_source (study_id, date, source)
    2. biomarker_readings: 新增 version_id (int, default=1, not null) — 乐观锁
       唯一索引 uq_readings_study_ts_loinc (study_id, sampled_at, loinc_code)

设计选择：
    - 用 CREATE UNIQUE INDEX 而非 ALTER TABLE ADD CONSTRAINT —— SQLite dialect
      不支持 ALTER of constraints；CREATE UNIQUE INDEX 在所有主流 SQL 方言均可用，
      且语义等价（ORM 侧仍声明 UniqueConstraint，Alembic 侧用 index 承载）。
    - 保留 server_default='1'，避免旧数据 NULL 触发 not-null 违反。
    - downgrade 严格反向：先删索引、再删列（顺序反转避免依赖失败）。

Downgrade 策略（round-trip 可验证）：
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
    # 唯一索引（跨方言，SQLite/PostgreSQL/MySQL 通用）
    op.create_index(
        'uq_snapshots_study_date_source',
        'axis_snapshots',
        ['study_id', 'date', 'source'],
        unique=True,
    )

    # --- biomarker_readings: version_id 乐观锁 ---
    op.add_column(
        'biomarker_readings',
        sa.Column('version_id', sa.Integer(), nullable=False, server_default='1'),
    )
    op.create_index(
        'uq_readings_study_ts_loinc',
        'biomarker_readings',
        ['study_id', 'sampled_at', 'loinc_code'],
        unique=True,
    )


def downgrade() -> None:
    # 严格反向：先删索引、再删列（顺序反转避免依赖失败）
    op.drop_index(
        'uq_readings_study_ts_loinc',
        table_name='biomarker_readings',
    )
    op.drop_column('biomarker_readings', 'version_id')

    op.drop_index(
        'uq_snapshots_study_date_source',
        table_name='axis_snapshots',
    )
    op.drop_column('axis_snapshots', 'version_id')
