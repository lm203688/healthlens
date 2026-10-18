"""009 补齐 users 表列级缺口（D0 冒烟枪修复）。

Revision ID: 009_users_missing_columns
Revises: 008_federated_optimistic_lock
Create Date: 2026-10-18

背景（10-16 全面评估报告 N1 / 10-17 复验）：
    全新部署 ``alembic upgrade head`` 后注册即崩 ``no such column: users.is_active``。
    根因分层：
      1. 表级缺口——v0.31.0 的 007_add_remaining_models 已补齐 32 张表（已闭合）；
      2. **列级缺口**——001_initial 建 users 时未含 is_active / nickname /
         referral_code / utm_* 六列，后续迁移只加过 totp/region 列，从未补这六列。
    测试路径 ``Base.metadata.create_all`` 一直掩盖该缺口（conftest.py:32），
    生产 alembic 路径直接暴露。

本迁移以 ORM 声明为单一真源补齐六列（app/models/user.py:17-23）：
    is_active     Boolean not null server_default '1'   （旧行默认激活，避免 NULL 违约）
    nickname      String(100) nullable
    utm_source    String(100) nullable
    utm_medium    String(100) nullable
    utm_campaign  String(200) nullable
    referral_code String(50) nullable

设计选择：
    - is_active 必须带 server_default：生产库已有用户行，无默认值会 not-null 违约；
    - 其余五列可空，无需默认值；
    - downgrade 严格反向删列（与 008 的"不删表不删数据"原则一致——删列是 schema
      回滚，不动行数据；且这些列在 downgrade 前的版本里本就不存在，删除即恢复原状）。
"""
from alembic import op
import sqlalchemy as sa


revision = '009_users_missing_columns'
down_revision = '008_federated_optimistic_lock'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users.is_active：活跃标志（ORM server_default="1"，Python default=True）
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
    )
    # users.nickname：显示名（可空）
    op.add_column(
        'users',
        sa.Column('nickname', sa.String(100), nullable=True),
    )
    # users.utm_*：获客归因（可空）
    op.add_column(
        'users',
        sa.Column('utm_source', sa.String(100), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('utm_medium', sa.String(100), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('utm_campaign', sa.String(200), nullable=True),
    )
    # users.referral_code：推荐码（可空）
    op.add_column(
        'users',
        sa.Column('referral_code', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    # 严格反向：删除 upgrade 添加的六列（恢复 008 时的 schema 原状）
    op.drop_column('users', 'referral_code')
    op.drop_column('users', 'utm_campaign')
    op.drop_column('users', 'utm_medium')
    op.drop_column('users', 'utm_source')
    op.drop_column('users', 'nickname')
    op.drop_column('users', 'is_active')
