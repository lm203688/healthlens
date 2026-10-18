"""010 删除 data_connections 孤儿列 source_name（ORM/迁移反向漂移修复）。

Revision ID: 010_drop_orphan_source_name
Revises: 009_users_missing_columns
Create Date: 2026-10-18

背景（2026-10-18 列级 parity 测试实证）：
    ``tests/lib/test_schema_column_parity.py::test_no_extra_columns`` 发现
    迁移 001_initial 创建了 ``data_connections.source_name``(String(200))，
    但 ORM（app/models/data_connection.py）从未声明该列，全代码库零引用
    （grep app/ tests/ tools/ 无命中）。这是 ORM↔迁移的**反向漂移**：
    009 修的是"迁移缺列"（少建），本迁移修的是"迁移多列"（多建）。

设计选择：
    - 以 ORM 为单一真源（app/models/data_connection.py），删除孤儿列；
    - downgrade 恢复该列（可空 String(200)，无默认值）——严格可逆；
    - 不碰任何数据行：SQLite/PostgreSQL 的 DROP COLUMN 均保留行数据。
"""
from alembic import op
import sqlalchemy as sa


revision = '010_drop_orphan_source_name'
down_revision = '009_users_missing_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('data_connections', 'source_name')


def downgrade() -> None:
    op.add_column(
        'data_connections',
        sa.Column('source_name', sa.String(200), nullable=True),
    )
