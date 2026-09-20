"""新增 wellness 自测闭环表与运行时审计表

Revision ID: 004_add_checkin_and_audit
Revises: 003_add_totp_columns
Create Date: 2026-09-20

- wellness_checkins: 用户 wellness 自测记录（能量/消化/睡眠 1-5 分 + 备注）
- audit_events: 简化版运行时审计事件表
"""
from alembic import op
import sqlalchemy as sa


revision = '004_add_checkin_and_audit'
down_revision = '003_add_totp_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'wellness_checkins',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('energy_score', sa.Integer(), nullable=False),
        sa.Column('digestion_score', sa.Integer(), nullable=False),
        sa.Column('sleep_score', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('checkin_date', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_wellness_checkins_user_id', 'wellness_checkins', ['user_id'])

    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('endpoint', sa.String(80), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('severity', sa.Integer(), server_default='1'),
        sa.Column('detail', sa.Text(), nullable=True),
    )
    op.create_index('ix_audit_events_user_id', 'audit_events', ['user_id'])
    op.create_index('ix_audit_events_endpoint', 'audit_events', ['endpoint'])
    op.create_index('ix_audit_events_event_type', 'audit_events', ['event_type'])


def downgrade() -> None:
    op.drop_table('audit_events')
    op.drop_table('wellness_checkins')
