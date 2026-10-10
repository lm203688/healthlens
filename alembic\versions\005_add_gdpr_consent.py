"""新增 GDPR 同意记录持久化表

Revision ID: 005_add_gdpr_consent
Revises: 004_add_checkin_and_audit
Create Date: 2026-10-09

- gdpr_consents: 用户 GDPR 同意记录持久化（替代内存 dict，重启不丢、多 worker 一致）
"""
from alembic import op
import sqlalchemy as sa


revision = '005_add_gdpr_consent'
down_revision = '004_add_checkin_and_audit'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gdpr_consents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('accepted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('accepted_at', sa.String(50), nullable=True),
        sa.Column('version', sa.String(10), nullable=False, server_default='2.0'),
        sa.Column('purposes', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
    )
    op.create_index('ix_gdpr_consents_user_id', 'gdpr_consents', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_gdpr_consents_user_id', table_name='gdpr_consents')
    op.drop_table('gdpr_consents')
