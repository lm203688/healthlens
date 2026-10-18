"""补齐 32 张缺失的 ORM 表迁移

Revision ID: 007_add_remaining_models
Revises: 006_add_region_jurisdiction
Create Date: 2026-10-17

背景：v0.30.0 全新部署 `alembic upgrade head` 后注册即崩
(`no such column: users.is_active`)，根因是 56 张 ORM 表里
32 张没有对应迁移，生产靠 `Base.metadata.create_all`
兜底。本迁移把差异补齐，使纯 alembic 路径可跑通。

生成方式：`python tools/gen_schema_migration.py`。人工复核后合并。
"""
from alembic import op
import sqlalchemy as sa


revision = '007_add_remaining_models'
down_revision = '006_add_region_jurisdiction'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tcm_classical_books
    op.create_table('tcm_classical_books',
    sa.Column('title', sa.String(200)),
    sa.Column('author', sa.String(200),
        nullable=True),
    sa.Column('dynasty', sa.String(100),
        nullable=True),
    sa.Column('year_text', sa.String(200),
        nullable=True),
    sa.Column('category', sa.String(100),
        nullable=True),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # food_therapy_recipes
    op.create_table('food_therapy_recipes',
    sa.Column('name', sa.String(200)),
    sa.Column('source_book', sa.String(200),
        nullable=True),
    sa.Column('dynasty', sa.String(100),
        nullable=True),
    sa.Column('category', sa.String(100),
        nullable=True),
    sa.Column('ingredients', sa.JSON,
        nullable=True),
    sa.Column('indications', sa.Text,
        nullable=True),
    sa.Column('method', sa.Text,
        nullable=True),
    sa.Column('constitution_types', sa.JSON,
        nullable=True),
    sa.Column('syndrome_keywords', sa.JSON,
        nullable=True),
    sa.Column('seasonal', sa.String(50),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # classical_formulas
    op.create_table('classical_formulas',
    sa.Column('formula_name', sa.String(200)),
    sa.Column('source_book', sa.String(200),
        nullable=True),
    sa.Column('dynasty', sa.String(100),
        nullable=True),
    sa.Column('composition', sa.JSON,
        nullable=True),
    sa.Column('indications', sa.Text,
        nullable=True),
    sa.Column('method', sa.Text,
        nullable=True),
    sa.Column('syndrome_code', sa.String(50),
        nullable=True),
    sa.Column('constitution_types', sa.JSON,
        nullable=True),
    sa.Column('modifications', sa.JSON,
        nullable=True),
    sa.Column('classical_reference', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # non_pharma_treatments
    op.create_table('non_pharma_treatments',
    sa.Column('treatment_type', sa.String(50)),
    sa.Column('treatment_type_name', sa.String(100),
        nullable=True),
    sa.Column('name', sa.String(200)),
    sa.Column('source_book', sa.String(200),
        nullable=True),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('indications', sa.Text,
        nullable=True),
    sa.Column('constitution_types', sa.JSON,
        nullable=True),
    sa.Column('syndrome_keywords', sa.JSON,
        nullable=True),
    sa.Column('instructions', sa.JSON,
        nullable=True),
    sa.Column('frequency', sa.String(100),
        nullable=True),
    sa.Column('duration', sa.String(100),
        nullable=True),
    sa.Column('precautions', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # user_points
    op.create_table('user_points',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('balance', sa.Numeric(15, 2)),
    sa.Column('total_earned', sa.Numeric(15, 2)),
    sa.Column('total_spent', sa.Numeric(15, 2)),
    sa.Column('lifetime_value', sa.Numeric(15, 2)),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_user_points_user_id', 'user_points', ['user_id'])

    # point_transactions
    op.create_table('point_transactions',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('tx_type', sa.String(10)),
    sa.Column('amount', sa.Numeric(15, 2)),
    sa.Column('balance_after', sa.Numeric(15, 2)),
    sa.Column('source', sa.String(50)),
    sa.Column('source_id', sa.String(36),
        nullable=True),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('extra_data', sa.JSON,
        nullable=True),
    sa.Column('expired_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_point_transactions_user_id', 'point_transactions', ['user_id'])

    # point_rules
    op.create_table('point_rules',
    sa.Column('rule_code', sa.String(50)),
    sa.Column('rule_name', sa.String(100)),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('action_type', sa.String(20)),
    sa.Column('base_points', sa.Numeric(10, 2)),
    sa.Column('multiplier_formula', sa.String(200),
        nullable=True),
    sa.Column('daily_limit', sa.Integer,
        nullable=True),
    sa.Column('monthly_limit', sa.Integer,
        nullable=True),
    sa.Column('is_active', sa.Boolean),
    sa.Column('priority', sa.Integer),
    sa.Column('category', sa.String(50),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # sleep_records
    op.create_table('sleep_records',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('sleep_date', sa.Date),
    sa.Column('bedtime', sa.String(5),
        nullable=True),
    sa.Column('wake_time', sa.String(5),
        nullable=True),
    sa.Column('sleep_latency_min', sa.Integer,
        nullable=True),
    sa.Column('total_duration_min', sa.Integer,
        nullable=True),
    sa.Column('deep_sleep_min', sa.Numeric,
        nullable=True),
    sa.Column('light_sleep_min', sa.Numeric,
        nullable=True),
    sa.Column('rem_sleep_min', sa.Numeric,
        nullable=True),
    sa.Column('awake_min', sa.Numeric,
        nullable=True),
    sa.Column('sleep_efficiency', sa.Numeric,
        nullable=True),
    sa.Column('awakenings_count', sa.Integer,
        nullable=True),
    sa.Column('hrv_avg', sa.Numeric,
        nullable=True),
    sa.Column('hrv_recovery', sa.Numeric,
        nullable=True),
    sa.Column('room_temp', sa.Numeric,
        nullable=True),
    sa.Column('subjective_score', sa.Integer,
        nullable=True),
    sa.Column('sleep_notes', sa.Text,
        nullable=True),
    sa.Column('source', sa.String(50),
        nullable=True),
    sa.Column('raw_data', sa.JSON,
        nullable=True),
    sa.Column('sleep_score', sa.Numeric,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_sleep_records_sleep_score', 'sleep_records', ['sleep_score'])
    op.create_index('ix_sleep_records_sleep_date', 'sleep_records', ['sleep_date'])
    op.create_index('ix_sleep_records_user_id', 'sleep_records', ['user_id'])

    # sleep_checklists
    op.create_table('sleep_checklists',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('checklist_date', sa.Date),
    sa.Column('warm_bath', sa.Boolean,
        nullable=True),
    sa.Column('blue_light_off', sa.Boolean,
        nullable=True),
    sa.Column('room_temp_ok', sa.Boolean,
        nullable=True),
    sa.Column('herbal_drink', sa.Boolean,
        nullable=True),
    sa.Column('meditation_done', sa.Boolean,
        nullable=True),
    sa.Column('all_completed', sa.Boolean,
        nullable=True),
    sa.Column('completion_time', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_sleep_checklists_checklist_date', 'sleep_checklists', ['checklist_date'])
    op.create_index('ix_sleep_checklists_user_id', 'sleep_checklists', ['user_id'])

    # repair_scores
    op.create_table('repair_scores',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('score_date', sa.Date),
    sa.Column('total_score', sa.Numeric,
        nullable=True),
    sa.Column('repair_age', sa.Numeric,
        nullable=True),
    sa.Column('calendar_age', sa.Integer,
        nullable=True),
    sa.Column('percentile', sa.Numeric,
        nullable=True),
    sa.Column('deep_sleep_score', sa.Numeric,
        nullable=True),
    sa.Column('hrv_recovery_score', sa.Numeric,
        nullable=True),
    sa.Column('inflammation_score', sa.Numeric,
        nullable=True),
    sa.Column('exercise_adherence_score', sa.Numeric,
        nullable=True),
    sa.Column('nutrition_score', sa.Numeric,
        nullable=True),
    sa.Column('circadian_score', sa.Numeric,
        nullable=True),
    sa.Column('subjective_energy_score', sa.Numeric,
        nullable=True),
    sa.Column('weights', sa.JSON,
        nullable=True),
    sa.Column('input_snapshot', sa.JSON,
        nullable=True),
    sa.Column('damage_analysis', sa.JSON,
        nullable=True),
    sa.Column('sources', sa.JSON,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_repair_scores_score_date', 'repair_scores', ['score_date'])
    op.create_index('ix_repair_scores_user_id', 'repair_scores', ['user_id'])
    op.create_index('ix_repair_scores_total_score', 'repair_scores', ['total_score'])

    # seo_pages
    op.create_table('seo_pages',
    sa.Column('slug', sa.String(255)),
    sa.Column('title', sa.String(500)),
    sa.Column('meta_description', sa.String(1000)),
    sa.Column('meta_keywords', sa.String(500)),
    sa.Column('content_html', sa.Text),
    sa.Column('structured_data', sa.JSON,
        nullable=True),
    sa.Column('category', sa.String(100)),
    sa.Column('heading', sa.String(500),
        nullable=True),
    sa.Column('keywords', sa.Text),
    sa.Column('status', sa.String(20),
        server_default='draft'),
    sa.Column('published_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('word_count', sa.Integer),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_seo_pages_published_at', 'seo_pages', ['published_at'])
    op.create_index('ix_seo_pages_category', 'seo_pages', ['category'])
    op.create_index('ix_seo_pages_slug', 'seo_pages', ['slug'])

    # seo_page_templates
    op.create_table('seo_page_templates',
    sa.Column('template_name', sa.String(255)),
    sa.Column('template_html', sa.Text),
    sa.Column('schema_types', sa.JSON,
        nullable=True),
    sa.Column('category', sa.String(100)),
    sa.Column('created_at', sa.DateTime(timezone=False),
        nullable=True,
        server_default=sa.func.now()),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_seo_page_templates_category', 'seo_page_templates', ['category'])

    # keyword_clusters
    op.create_table('keyword_clusters',
    sa.Column('keyword', sa.String(255)),
    sa.Column('search_volume', sa.Integer,
        nullable=True),
    sa.Column('difficulty', sa.Integer,
        nullable=True),
    sa.Column('intent', sa.String(20)),
    sa.Column('category', sa.String(100)),
    sa.Column('related_keywords', sa.JSON,
        nullable=True),
    sa.Column('status', sa.String(20),
        server_default='active'),
    sa.Column('created_at', sa.DateTime(timezone=False),
        nullable=True,
        server_default=sa.func.now()),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_keyword_clusters_category', 'keyword_clusters', ['category'])
    op.create_index('ix_keyword_clusters_category_status', 'keyword_clusters', ['category', 'status'])
    op.create_index('ix_keyword_clusters_keyword', 'keyword_clusters', ['keyword'])

    # analytics_events
    op.create_table('analytics_events',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id'),
        nullable=True),
    sa.Column('event_type', sa.String(100)),
    sa.Column('page', sa.String(500)),
    sa.Column('element', sa.String(255),
        nullable=True),
    sa.Column('metadata_', sa.JSON,
        nullable=True),
    sa.Column('session_id', sa.String(100),
        nullable=True),
    sa.Column('ip_hash', sa.String(64),
        nullable=True),
    sa.Column('user_agent', sa.String(500),
        nullable=True),
    sa.Column('referrer', sa.String(1000),
        nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_analytics_events_session_created', 'analytics_events', ['session_id', 'created_at'])
    op.create_index('ix_analytics_events_session_id', 'analytics_events', ['session_id'])
    op.create_index('ix_analytics_events_event_type_created', 'analytics_events', ['event_type', 'created_at'])
    op.create_index('ix_analytics_events_created_at', 'analytics_events', ['created_at'])
    op.create_index('ix_analytics_events_event_type', 'analytics_events', ['event_type'])
    op.create_index('ix_analytics_events_user_id', 'analytics_events', ['user_id'])

    # analytics_sessions
    op.create_table('analytics_sessions',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id'),
        nullable=True),
    sa.Column('session_id', sa.String(100)),
    sa.Column('duration', sa.Integer,
        server_default='0'),
    sa.Column('duration_seconds', sa.Integer,
        server_default='0'),
    sa.Column('pages_visited', sa.JSON,
        nullable=True),
    sa.Column('actions_count', sa.Integer),
    sa.Column('device_type', sa.String(50),
        nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_analytics_sessions_created_at', 'analytics_sessions', ['created_at'])
    op.create_index('ix_analytics_sessions_session_id', 'analytics_sessions', ['session_id'])
    op.create_index('ix_analytics_sessions_user_id', 'analytics_sessions', ['user_id'])

    # conversion_records
    op.create_table('conversion_records',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id'),
        nullable=True),
    sa.Column('source', sa.String(50)),
    sa.Column('referrer_code', sa.String(255),
        nullable=True),
    sa.Column('landing_page', sa.String(500),
        nullable=True),
    sa.Column('conversion_type', sa.String(50)),
    sa.Column('metadata_', sa.JSON,
        nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_conversion_records_user_id', 'conversion_records', ['user_id'])
    op.create_index('ix_conversion_records_source_type', 'conversion_records', ['source', 'conversion_type'])
    op.create_index('ix_conversion_records_conversion_type', 'conversion_records', ['conversion_type'])
    op.create_index('ix_conversion_records_created_at', 'conversion_records', ['created_at'])
    op.create_index('ix_conversion_records_source', 'conversion_records', ['source'])

    # invite_codes
    op.create_table('invite_codes',
    sa.Column('code', sa.String(12)),
    sa.Column('inviter_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('claimant_id', sa.String(36),
        sa.ForeignKey('users.id'),
        nullable=True),
    sa.Column('status', sa.String(20),
        server_default='active'),
    sa.Column('is_claimed', sa.Boolean,
        server_default='0'),
    sa.Column('reward_points', sa.Integer),
    sa.Column('claimed_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_invite_codes_code', 'invite_codes', ['code'])
    op.create_index('ix_invite_codes_expires_at', 'invite_codes', ['expires_at'])
    op.create_index('ix_invite_codes_inviter_id', 'invite_codes', ['inviter_id'])
    op.create_index('ix_invite_codes_claimant_id', 'invite_codes', ['claimant_id'])

    # share_records
    op.create_table('share_records',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('content_type', sa.String(50)),
    sa.Column('content_id', sa.String(36),
        nullable=True),
    sa.Column('share_url', sa.String(1000),
        nullable=True),
    sa.Column('platform', sa.String(20)),
    sa.Column('click_count', sa.Integer),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_share_records_user_id', 'share_records', ['user_id'])

    # shared_reports
    op.create_table('shared_reports',
    sa.Column('share_token', sa.String(32)),
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('report_type', sa.String(50)),
    sa.Column('title', sa.String(200)),
    sa.Column('summary_text', sa.Text),
    sa.Column('report_data', sa.JSON),
    sa.Column('is_public', sa.Boolean,
        server_default='1'),
    sa.Column('view_count', sa.Integer),
    sa.Column('share_count', sa.Integer),
    sa.Column('expires_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('og_title', sa.String(200),
        nullable=True),
    sa.Column('og_description', sa.String(500),
        nullable=True),
    sa.Column('og_image_url', sa.String(1000),
        nullable=True),
    sa.Column('health_score', sa.Integer,
        nullable=True),
    sa.Column('risk_level', sa.String(20),
        nullable=True),
    sa.Column('extra_data', sa.JSON,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_shared_reports_user_id', 'shared_reports', ['user_id'])
    op.create_index('ix_shared_reports_expires_at', 'shared_reports', ['expires_at'])
    op.create_index('ix_shared_reports_share_token', 'shared_reports', ['share_token'])

    # referral_tiers
    op.create_table('referral_tiers',
    sa.Column('tier_level', sa.Integer),
    sa.Column('tier_name', sa.String(50)),
    sa.Column('min_invites', sa.Integer),
    sa.Column('max_invites', sa.Integer,
        nullable=True),
    sa.Column('reward_multiplier', sa.Numeric(5, 2)),
    sa.Column('bonus_points', sa.Integer),
    sa.Column('is_active', sa.Boolean,
        server_default='1'),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # referral_relationships
    op.create_table('referral_relationships',
    sa.Column('inviter_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('invitee_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('level', sa.Integer,
        server_default='1'),
    sa.Column('reward_claimed', sa.Boolean,
        server_default='0'),
    sa.Column('reward_amount', sa.Integer),
    sa.Column('claimed_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('invite_code_used', sa.String(12),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_referral_relationships_invitee_id', 'referral_relationships', ['invitee_id'])
    op.create_index('ix_referral_relationships_inviter_id', 'referral_relationships', ['inviter_id'])

    # referral_rebates
    op.create_table('referral_rebates',
    sa.Column('inviter_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('invitee_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('level', sa.Integer),
    sa.Column('source_tx_id', sa.String(36),
        sa.ForeignKey('point_transactions.id'),
        nullable=True),
    sa.Column('rebate_percent', sa.Numeric(5, 2)),
    sa.Column('rebate_points', sa.Integer),
    sa.Column('description', sa.String(200),
        nullable=True),
    sa.Column('is_processed', sa.Boolean,
        server_default='0'),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_referral_rebates_invitee_id', 'referral_rebates', ['invitee_id'])
    op.create_index('ix_referral_rebates_inviter_id', 'referral_rebates', ['inviter_id'])

    # point_packages
    op.create_table('point_packages',
    sa.Column('package_code', sa.String(50)),
    sa.Column('package_name', sa.String(100)),
    sa.Column('points_amount', sa.Integer),
    sa.Column('bonus_points', sa.Integer),
    sa.Column('price_cny', sa.Numeric(10, 2)),
    sa.Column('original_price', sa.Numeric(10, 2),
        nullable=True),
    sa.Column('is_active', sa.Boolean,
        server_default='1'),
    sa.Column('is_popular', sa.Boolean,
        server_default='0'),
    sa.Column('sort_order', sa.Integer),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('extra_data', sa.JSON,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )

    # point_orders
    op.create_table('point_orders',
    sa.Column('order_no', sa.String(32)),
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('package_id', sa.String(36),
        sa.ForeignKey('point_packages.id')),
    sa.Column('package_code', sa.String(50)),
    sa.Column('points_amount', sa.Integer),
    sa.Column('bonus_points', sa.Integer),
    sa.Column('total_points', sa.Integer),
    sa.Column('price_cny', sa.Numeric(10, 2)),
    sa.Column('payment_method', sa.String(20)),
    sa.Column('payment_status', sa.String(20)),
    sa.Column('paid_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('transaction_id', sa.String(100),
        nullable=True),
    sa.Column('points_credited', sa.Boolean,
        server_default='0'),
    sa.Column('credited_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('credited_tx_id', sa.String(36),
        sa.ForeignKey('point_transactions.id'),
        nullable=True),
    sa.Column('extra_data', sa.JSON,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_point_orders_user_id', 'point_orders', ['user_id'])
    op.create_index('ix_point_orders_order_no', 'point_orders', ['order_no'])

    # verification_codes
    op.create_table('verification_codes',
    sa.Column('phone', sa.String(20)),
    sa.Column('code', sa.String(10)),
    sa.Column('purpose', sa.String(20)),
    sa.Column('created_at', sa.DateTime(timezone=False)),
    sa.Column('expires_at', sa.DateTime(timezone=False)),
    sa.Column('used', sa.Boolean),
    sa.Column('attempts', sa.Integer),
    sa.Column('id', sa.String(36),
        primary_key=True),
    )
    op.create_index('ix_verification_codes_phone_purpose', 'verification_codes', ['phone', 'purpose'])
    op.create_index('ix_verification_codes_phone', 'verification_codes', ['phone'])

    # field_consents
    op.create_table('field_consents',
    sa.Column('user_id', sa.String(36)),
    sa.Column('field_path', sa.String(200)),
    sa.Column('jurisdiction', sa.String(10)),
    sa.Column('purpose', sa.String(50)),
    sa.Column('accepted', sa.Boolean),
    sa.Column('accepted_at', sa.String(50),
        nullable=True),
    sa.Column('version', sa.String(10)),
    sa.Column('note', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_field_consents_jurisdiction', 'field_consents', ['jurisdiction'])
    op.create_index('ix_field_consents_purpose', 'field_consents', ['purpose'])
    op.create_index('ix_field_consents_field_path', 'field_consents', ['field_path'])
    op.create_index('uq_field_consent_unique', 'field_consents', ['user_id', 'field_path', 'jurisdiction', 'purpose'])
    op.create_index('ix_field_consents_user_id', 'field_consents', ['user_id'])
    op.create_index('ix_field_consent_user_jurisdiction', 'field_consents', ['user_id', 'jurisdiction'])

    # longitudinal_studies
    op.create_table('longitudinal_studies',
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('name', sa.String(200)),
    sa.Column('cohort', sa.String(20)),
    sa.Column('status', sa.String(20)),
    sa.Column('start_date', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('end_date', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('data_residency_region', sa.String(10)),
    sa.Column('baseline_snapshot_id', sa.String(36),
        nullable=True),
    sa.Column('protocol', sa.JSON,
        nullable=True),
    sa.Column('consent_version', sa.String(50),
        nullable=True),
    sa.Column('notes', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_longitudinal_studies_user_id', 'longitudinal_studies', ['user_id'])
    op.create_index('ix_studies_region', 'longitudinal_studies', ['data_residency_region'])
    op.create_index('ix_studies_user_status', 'longitudinal_studies', ['user_id', 'status'])

    # axis_snapshots
    op.create_table('axis_snapshots',
    sa.Column('study_id', sa.String(36),
        sa.ForeignKey('longitudinal_studies.id')),
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('captured_at', sa.DateTime(timezone=False)),
    sa.Column('date', sa.String(10)),
    sa.Column('jurisdiction', sa.String(10)),
    sa.Column('axis_scores', sa.JSON,
        nullable=True),
    sa.Column('overall_score', sa.Numeric(5, 2),
        nullable=True),
    sa.Column('weak_axes', sa.JSON,
        nullable=True),
    sa.Column('input_fingerprint', sa.String(64),
        nullable=True),
    sa.Column('input_summary', sa.JSON,
        nullable=True),
    sa.Column('source', sa.String(30)),
    sa.Column('notes', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_snapshots_user_date', 'axis_snapshots', ['user_id', 'date'])
    op.create_index('ix_axis_snapshots_user_id', 'axis_snapshots', ['user_id'])
    op.create_index('ix_axis_snapshots_study_id', 'axis_snapshots', ['study_id'])
    op.create_index('ix_snapshots_study_date', 'axis_snapshots', ['study_id', 'date'])

    # intervention_events
    op.create_table('intervention_events',
    sa.Column('study_id', sa.String(36),
        sa.ForeignKey('longitudinal_studies.id')),
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('intervention_type', sa.String(50)),
    sa.Column('target_axis', sa.String(2),
        nullable=True),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('intensity', sa.Numeric(4, 3),
        nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=False)),
    sa.Column('ended_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('outcome_note', sa.Text,
        nullable=True),
    sa.Column('intervention_meta', sa.JSON,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_interventions_type', 'intervention_events', ['intervention_type'])
    op.create_index('ix_interventions_study_time', 'intervention_events', ['study_id', 'started_at'])
    op.create_index('ix_intervention_events_user_id', 'intervention_events', ['user_id'])
    op.create_index('ix_intervention_events_study_id', 'intervention_events', ['study_id'])

    # biomarker_readings
    op.create_table('biomarker_readings',
    sa.Column('study_id', sa.String(36),
        sa.ForeignKey('longitudinal_studies.id')),
    sa.Column('user_id', sa.String(36),
        sa.ForeignKey('users.id')),
    sa.Column('loinc_code', sa.String(50)),
    sa.Column('loinc_name', sa.String(200)),
    sa.Column('value_numeric', sa.Numeric(15, 5),
        nullable=True),
    sa.Column('value_string', sa.Text,
        nullable=True),
    sa.Column('value_unit', sa.String(50),
        nullable=True),
    sa.Column('sampled_at', sa.DateTime(timezone=False)),
    sa.Column('lab_source', sa.String(100),
        nullable=True),
    sa.Column('reference_low', sa.Numeric(15, 5),
        nullable=True),
    sa.Column('reference_high', sa.Numeric(15, 5),
        nullable=True),
    sa.Column('notes', sa.Text,
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_biomarker_readings_user_id', 'biomarker_readings', ['user_id'])
    op.create_index('ix_readings_loinc', 'biomarker_readings', ['loinc_code'])
    op.create_index('ix_biomarker_readings_study_id', 'biomarker_readings', ['study_id'])
    op.create_index('ix_readings_study_time', 'biomarker_readings', ['study_id', 'sampled_at'])

    # partners
    op.create_table('partners',
    sa.Column('name', sa.String(200)),
    sa.Column('contact_email', sa.String(255)),
    sa.Column('status', sa.String(20),
        server_default='pending'),
    sa.Column('description', sa.Text,
        nullable=True),
    sa.Column('brand_name', sa.String(100),
        nullable=True),
    sa.Column('allowed_endpoints', sa.Text,
        nullable=True),
    sa.Column('rate_limit_per_min', sa.Integer),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_partners_status', 'partners', ['status'])
    op.create_index('ix_partners_email', 'partners', ['contact_email'])

    # partner_api_keys
    op.create_table('partner_api_keys',
    sa.Column('partner_id', sa.String(36),
        sa.ForeignKey('partners.id', ondelete='CASCADE')),
    sa.Column('key_hash', sa.String(64)),
    sa.Column('key_prefix', sa.String(32)),
    sa.Column('name', sa.String(100)),
    sa.Column('status', sa.String(20),
        server_default='active'),
    sa.Column('last_used_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=False),
        nullable=True),
    sa.Column('note', sa.String(255),
        nullable=True),
    sa.Column('id', sa.String(36),
        primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=False),
        server_default=sa.func.now()),
    )
    op.create_index('ix_partner_api_keys_partner_id', 'partner_api_keys', ['partner_id'])
    op.create_index('ix_partner_api_keys_partner_status', 'partner_api_keys', ['partner_id', 'status'])
    op.create_index('ix_partner_api_keys_key_hash', 'partner_api_keys', ['key_hash'])



def downgrade() -> None:
    op.drop_index('ix_partner_api_keys_partner_id', table_name='partner_api_keys')
    op.drop_index('ix_partner_api_keys_partner_status', table_name='partner_api_keys')
    op.drop_index('ix_partner_api_keys_key_hash', table_name='partner_api_keys')
    op.drop_table('partner_api_keys')

    op.drop_index('ix_partners_status', table_name='partners')
    op.drop_index('ix_partners_email', table_name='partners')
    op.drop_table('partners')

    op.drop_index('ix_biomarker_readings_user_id', table_name='biomarker_readings')
    op.drop_index('ix_readings_loinc', table_name='biomarker_readings')
    op.drop_index('ix_biomarker_readings_study_id', table_name='biomarker_readings')
    op.drop_index('ix_readings_study_time', table_name='biomarker_readings')
    op.drop_table('biomarker_readings')

    op.drop_index('ix_interventions_type', table_name='intervention_events')
    op.drop_index('ix_interventions_study_time', table_name='intervention_events')
    op.drop_index('ix_intervention_events_user_id', table_name='intervention_events')
    op.drop_index('ix_intervention_events_study_id', table_name='intervention_events')
    op.drop_table('intervention_events')

    op.drop_index('ix_snapshots_user_date', table_name='axis_snapshots')
    op.drop_index('ix_axis_snapshots_user_id', table_name='axis_snapshots')
    op.drop_index('ix_axis_snapshots_study_id', table_name='axis_snapshots')
    op.drop_index('ix_snapshots_study_date', table_name='axis_snapshots')
    op.drop_table('axis_snapshots')

    op.drop_index('ix_longitudinal_studies_user_id', table_name='longitudinal_studies')
    op.drop_index('ix_studies_region', table_name='longitudinal_studies')
    op.drop_index('ix_studies_user_status', table_name='longitudinal_studies')
    op.drop_table('longitudinal_studies')

    op.drop_index('ix_field_consents_jurisdiction', table_name='field_consents')
    op.drop_index('ix_field_consents_purpose', table_name='field_consents')
    op.drop_index('ix_field_consents_field_path', table_name='field_consents')
    op.drop_index('uq_field_consent_unique', table_name='field_consents')
    op.drop_index('ix_field_consents_user_id', table_name='field_consents')
    op.drop_index('ix_field_consent_user_jurisdiction', table_name='field_consents')
    op.drop_table('field_consents')

    op.drop_index('ix_verification_codes_phone_purpose', table_name='verification_codes')
    op.drop_index('ix_verification_codes_phone', table_name='verification_codes')
    op.drop_table('verification_codes')

    op.drop_index('ix_point_orders_user_id', table_name='point_orders')
    op.drop_index('ix_point_orders_order_no', table_name='point_orders')
    op.drop_table('point_orders')

    op.drop_table('point_packages')

    op.drop_index('ix_referral_rebates_invitee_id', table_name='referral_rebates')
    op.drop_index('ix_referral_rebates_inviter_id', table_name='referral_rebates')
    op.drop_table('referral_rebates')

    op.drop_index('ix_referral_relationships_invitee_id', table_name='referral_relationships')
    op.drop_index('ix_referral_relationships_inviter_id', table_name='referral_relationships')
    op.drop_table('referral_relationships')

    op.drop_table('referral_tiers')

    op.drop_index('ix_shared_reports_user_id', table_name='shared_reports')
    op.drop_index('ix_shared_reports_expires_at', table_name='shared_reports')
    op.drop_index('ix_shared_reports_share_token', table_name='shared_reports')
    op.drop_table('shared_reports')

    op.drop_index('ix_share_records_user_id', table_name='share_records')
    op.drop_table('share_records')

    op.drop_index('ix_invite_codes_code', table_name='invite_codes')
    op.drop_index('ix_invite_codes_expires_at', table_name='invite_codes')
    op.drop_index('ix_invite_codes_inviter_id', table_name='invite_codes')
    op.drop_index('ix_invite_codes_claimant_id', table_name='invite_codes')
    op.drop_table('invite_codes')

    op.drop_index('ix_conversion_records_user_id', table_name='conversion_records')
    op.drop_index('ix_conversion_records_source_type', table_name='conversion_records')
    op.drop_index('ix_conversion_records_conversion_type', table_name='conversion_records')
    op.drop_index('ix_conversion_records_created_at', table_name='conversion_records')
    op.drop_index('ix_conversion_records_source', table_name='conversion_records')
    op.drop_table('conversion_records')

    op.drop_index('ix_analytics_sessions_created_at', table_name='analytics_sessions')
    op.drop_index('ix_analytics_sessions_session_id', table_name='analytics_sessions')
    op.drop_index('ix_analytics_sessions_user_id', table_name='analytics_sessions')
    op.drop_table('analytics_sessions')

    op.drop_index('ix_analytics_events_session_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_session_id', table_name='analytics_events')
    op.drop_index('ix_analytics_events_event_type_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_created_at', table_name='analytics_events')
    op.drop_index('ix_analytics_events_event_type', table_name='analytics_events')
    op.drop_index('ix_analytics_events_user_id', table_name='analytics_events')
    op.drop_table('analytics_events')

    op.drop_index('ix_keyword_clusters_category', table_name='keyword_clusters')
    op.drop_index('ix_keyword_clusters_category_status', table_name='keyword_clusters')
    op.drop_index('ix_keyword_clusters_keyword', table_name='keyword_clusters')
    op.drop_table('keyword_clusters')

    op.drop_index('ix_seo_page_templates_category', table_name='seo_page_templates')
    op.drop_table('seo_page_templates')

    op.drop_index('ix_seo_pages_published_at', table_name='seo_pages')
    op.drop_index('ix_seo_pages_category', table_name='seo_pages')
    op.drop_index('ix_seo_pages_slug', table_name='seo_pages')
    op.drop_table('seo_pages')

    op.drop_index('ix_repair_scores_score_date', table_name='repair_scores')
    op.drop_index('ix_repair_scores_user_id', table_name='repair_scores')
    op.drop_index('ix_repair_scores_total_score', table_name='repair_scores')
    op.drop_table('repair_scores')

    op.drop_index('ix_sleep_checklists_checklist_date', table_name='sleep_checklists')
    op.drop_index('ix_sleep_checklists_user_id', table_name='sleep_checklists')
    op.drop_table('sleep_checklists')

    op.drop_index('ix_sleep_records_sleep_score', table_name='sleep_records')
    op.drop_index('ix_sleep_records_sleep_date', table_name='sleep_records')
    op.drop_index('ix_sleep_records_user_id', table_name='sleep_records')
    op.drop_table('sleep_records')

    op.drop_table('point_rules')

    op.drop_index('ix_point_transactions_user_id', table_name='point_transactions')
    op.drop_table('point_transactions')

    op.drop_index('ix_user_points_user_id', table_name='user_points')
    op.drop_table('user_points')

    op.drop_table('non_pharma_treatments')

    op.drop_table('classical_formulas')

    op.drop_table('food_therapy_recipes')

    op.drop_table('tcm_classical_books')

