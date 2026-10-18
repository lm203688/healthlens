"""补全迁移 - 新增 5 张表 (health_goals, goal_progress, notifications, risk_assessments, medication_adherence)

Revision ID: 002_add_missing_tables
Revises: 001_initial
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = '002_add_missing_tables'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid_type = sa.String(36)

    # Health Goals
    op.create_table('health_goals',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('goal_type', sa.String(50)),
        sa.Column('goal_name', sa.String(200)),
        sa.Column('target_value', sa.Numeric(10, 2)),
        sa.Column('current_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit', sa.String(50)),
        sa.Column('start_date', sa.DateTime()),
        sa.Column('target_date', sa.DateTime()),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('progress', sa.Numeric(5, 2), server_default='0'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('is_reminder_enabled', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Goal Progress
    op.create_table('goal_progress',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('goal_id', uuid_type, sa.ForeignKey('health_goals.id')),
        sa.Column('value', sa.Numeric(10, 2)),
        sa.Column('recorded_at', sa.DateTime()),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Notifications
    op.create_table('notifications',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('category', sa.String(50)),
        sa.Column('title', sa.String(200)),
        sa.Column('content', sa.Text),
        sa.Column('severity', sa.String(20), server_default='info'),
        sa.Column('is_read', sa.Boolean, server_default='false'),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('action_url', sa.String(500), nullable=True),
        sa.Column('action_label', sa.String(100), nullable=True),
        sa.Column('extra_data', sa.Text, nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Risk Assessments
    op.create_table('risk_assessments',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('risk_type', sa.String(50)),
        sa.Column('risk_level', sa.String(20)),
        sa.Column('risk_score', sa.Numeric(10, 2)),
        sa.Column('risk_probability', sa.Numeric(5, 2)),
        sa.Column('risk_factors', sa.Text, nullable=True),
        sa.Column('recommendations', sa.Text, nullable=True),
        sa.Column('references', sa.Text, nullable=True),
        sa.Column('input_snapshot', sa.Text, nullable=True),
        sa.Column('assessed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Medication Adherence
    op.create_table('medication_adherence',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('medication_id', uuid_type, sa.ForeignKey('medication_recommendations.id'), nullable=True),
        sa.Column('medication_name', sa.String(200)),
        sa.Column('prescribed_dose', sa.String(100), nullable=True),
        sa.Column('scheduled_at', sa.DateTime()),
        sa.Column('taken_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('is_late', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 修复 data_connections 表：添加 config 和 is_active 字段
    op.add_column('data_connections', sa.Column('config', sa.Text, nullable=True))
    op.add_column('data_connections', sa.Column('is_active', sa.Boolean, server_default='true'))


def downgrade() -> None:
    op.drop_table('medication_adherence')
    op.drop_table('risk_assessments')
    op.drop_table('notifications')
    op.drop_table('goal_progress')
    op.drop_table('health_goals')
    op.drop_column('data_connections', 'is_active')
    op.drop_column('data_connections', 'config')
