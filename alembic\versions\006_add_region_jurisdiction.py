"""Users 表新增 region / jurisdiction 字段

Revision ID: 006_add_region_jurisdiction
Revises: 005_add_gdpr_consent
Create Date: 2026-10-10

- users.region：数据平面部署区域（cn / sg / eu ...），PII 物理驻留地
- users.jurisdiction：Claims 策略所属法域，用于输出前按法域过滤字段
- 两者关系：jurisdiction 通常 == region，但同一部署可服务多法域时，jurisdiction
  由用户显式选择，region 保持部署区域不变。
- 默认 'cn' 兼容既有用户（PIPL 是首发法域）。

阶段 A4 落地：区域标识与数据驻留代码级约束的地基。
"""
from alembic import op
import sqlalchemy as sa


revision = '006_add_region_jurisdiction'
down_revision = '005_add_gdpr_consent'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # region 是数据驻留字段，用于强制 PII 不跨境。
    op.add_column(
        'users',
        sa.Column(
            'region',
            sa.String(length=8),
            nullable=False,
            server_default='cn',
        ),
    )
    op.create_index('ix_users_region', 'users', ['region'])

    # jurisdiction 是 Claims 策略路由字段，独立于 region。
    op.add_column(
        'users',
        sa.Column(
            'jurisdiction',
            sa.String(length=8),
            nullable=False,
            server_default='cn',
        ),
    )
    op.create_index('ix_users_jurisdiction', 'users', ['jurisdiction'])


def downgrade() -> None:
    op.drop_index('ix_users_jurisdiction', table_name='users')
    op.drop_column('users', 'jurisdiction')
    op.drop_index('ix_users_region', table_name='users')
    op.drop_column('users', 'region')
