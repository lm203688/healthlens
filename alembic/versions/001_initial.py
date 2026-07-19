"""初始迁移 - 创建所有表

Revision ID: 001_initial
Revises: -
Create Date: 2026-07-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import json


# revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 注意: UUID 使用 TEXT(36) 以兼容 SQLite 测试环境
    uuid_type = sa.String(36)

    # Users
    op.create_table('users',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('phone', sa.String(20)),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), server_default='patient'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Health Profiles
    op.create_table('health_profiles',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id'), unique=True),
        sa.Column('fhir_patient_id', sa.String(100)),
        sa.Column('name', sa.String(100)),
        sa.Column('gender', sa.String(10)),
        sa.Column('birth_date', sa.Date),
        sa.Column('blood_type', sa.String(10)),
        sa.Column('height_cm', sa.Numeric(5, 1)),
        sa.Column('weight_kg', sa.Numeric(5, 1)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Health Observations
    op.create_table('health_observations',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('loinc_code', sa.String(50)),
        sa.Column('loinc_name', sa.String(500)),
        sa.Column('value_numeric', sa.Numeric(15, 5)),
        sa.Column('value_string', sa.Text),
        sa.Column('value_unit', sa.String(50)),
        sa.Column('reference_range_low', sa.Numeric(15, 5)),
        sa.Column('reference_range_high', sa.Numeric(15, 5)),
        sa.Column('source', sa.String(100)),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_health_observations_user_id', 'health_observations', ['user_id'])
    op.create_index('ix_health_observations_recorded_at', 'health_observations', ['recorded_at'])

    # Health Records
    op.create_table('health_records',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, index=True),
        sa.Column('filename', sa.String(500)),
        sa.Column('file_path', sa.String(1000)),
        sa.Column('file_size', sa.Integer, default=0),
        sa.Column('content_type', sa.String(100)),
        sa.Column('status', sa.String(20), server_default='uploaded'),
        sa.Column('parse_result', sa.Text, nullable=True),
        sa.Column('observations_count', sa.Integer, default=0),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Diagnosis Results
    op.create_table('diagnosis_results',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('diagnosis_text', sa.Text),
        sa.Column('icd_code', sa.String(50)),
        sa.Column('confidence', sa.Numeric(4, 3)),
        sa.Column('severity', sa.String(50)),
        sa.Column('is_ai_generated', sa.Boolean, server_default='true'),
        sa.Column('reviewed_by', uuid_type, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Medication Recommendations
    op.create_table('medication_recommendations',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('diagnosis_id', uuid_type, sa.ForeignKey('diagnosis_results.id')),
        sa.Column('drug_name', sa.String(200)),
        sa.Column('drug_code', sa.String(50)),
        sa.Column('dosage', sa.String(100)),
        sa.Column('dosage_unit', sa.String(50)),
        sa.Column('frequency', sa.String(100)),
        sa.Column('route', sa.String(50)),
        sa.Column('pgx_evidence', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Prescriptions
    op.create_table('prescriptions',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('diagnosis_id', uuid_type, sa.ForeignKey('diagnosis_results.id'), nullable=True),
        sa.Column('prescription_no', sa.String(50), unique=True),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('medications', sa.JSON),
        sa.Column('notes', sa.Text),
        sa.Column('prescribed_at', sa.DateTime()),
        sa.Column('prescribed_by', uuid_type, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Data Connections
    op.create_table('data_connections',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('source_type', sa.String(50)),
        sa.Column('source_name', sa.String(200)),
        sa.Column('access_token', sa.Text),
        sa.Column('refresh_token', sa.Text),
        sa.Column('token_expires_at', sa.DateTime()),
        sa.Column('last_sync_at', sa.DateTime()),
        sa.Column('sync_status', sa.String(20), server_default='pending'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Pharmacogenomic Profiles
    op.create_table('pharmacogenomic_profiles',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('gene_symbol', sa.String(50)),
        sa.Column('phenotype', sa.String(100)),
        sa.Column('variant_rsid', sa.String(50)),
        sa.Column('genotype', sa.String(50)),
        sa.Column('source', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # === TCM Tables ===

    # TCM Profiles
    op.create_table('tcm_profiles',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id'), unique=True),
        sa.Column('constitution_type', sa.String(50)),
        sa.Column('constitution_score', sa.JSON),
        sa.Column('questionnaire_data', sa.JSON),
        sa.Column('assessed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Tongue Images
    op.create_table('tongue_images',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('image_url', sa.String(1000)),
        sa.Column('tongue_color', sa.String(50)),
        sa.Column('tongue_shape', sa.String(50)),
        sa.Column('coating_color', sa.String(50)),
        sa.Column('coating_quality', sa.String(50)),
        sa.Column('sublingual_vein', sa.String(50)),
        sa.Column('ai_analysis', sa.JSON),
        sa.Column('reviewed_by', uuid_type, nullable=True),
        sa.Column('recorded_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # TCM Syndrome Diagnoses
    op.create_table('tcm_syndrome_diagnoses',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('syndrome_code', sa.String(50)),
        sa.Column('syndrome_name', sa.String(200)),
        sa.Column('principle', sa.String(200)),
        sa.Column('confidence', sa.Numeric(4, 3)),
        sa.Column('evidence', sa.JSON),
        sa.Column('is_ai_generated', sa.Boolean, server_default='true'),
        sa.Column('reviewed_by', uuid_type, nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('diagnosis_id', uuid_type, nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # TCM Formula Recommendations
    op.create_table('tcm_formula_recommendations',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('syndrome_id', uuid_type, sa.ForeignKey('tcm_syndrome_diagnoses.id')),
        sa.Column('formula_name', sa.String(100)),
        sa.Column('formula_source', sa.String(200)),
        sa.Column('original_composition', sa.JSON),
        sa.Column('modified_composition', sa.JSON),
        sa.Column('additions', sa.JSON),
        sa.Column('subtractions', sa.JSON),
        sa.Column('dosage_instructions', sa.Text),
        sa.Column('formula_analysis', sa.JSON),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # TCM Formula Library
    op.create_table('tcm_formula_library',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('formula_name', sa.String(100), nullable=False),
        sa.Column('formula_name_en', sa.String(200)),
        sa.Column('source', sa.String(200)),
        sa.Column('category', sa.String(100)),
        sa.Column('composition', sa.JSON),
        sa.Column('dosage', sa.Text),
        sa.Column('indications', sa.Text),
        sa.Column('syndrome_code', sa.String(50)),
        sa.Column('modifications', sa.JSON),
        sa.Column('contraindications', sa.Text),
        sa.Column('modern_evidence', sa.JSON),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # TCM Herbs
    op.create_table('tcm_herbs',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('herb_name', sa.String(100), nullable=False),
        sa.Column('herb_name_en', sa.String(200)),
        sa.Column('pinyin', sa.String(100)),
        sa.Column('category', sa.String(100)),
        sa.Column('property', sa.String(50)),
        sa.Column('flavor', sa.String(100)),
        sa.Column('meridian', sa.String(200)),
        sa.Column('efficacy', sa.Text),
        sa.Column('usage_dosage', sa.Text),
        sa.Column('contraindications', sa.Text),
        sa.Column('chemical_components', sa.JSON),
        sa.Column('cyp450_metabolism', sa.JSON),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # TCM Delivery Orders
    op.create_table('tcm_delivery_orders',
        sa.Column('id', uuid_type, primary_key=True),
        sa.Column('user_id', uuid_type, sa.ForeignKey('users.id')),
        sa.Column('formula_id', uuid_type, sa.ForeignKey('tcm_formula_recommendations.id'), nullable=True),
        sa.Column('pharmacy_name', sa.String(200)),
        sa.Column('order_status', sa.String(20), server_default='pending'),
        sa.Column('tracking_number', sa.String(100)),
        sa.Column('delivery_address', sa.Text),
        sa.Column('total_fee', sa.Numeric(10, 2)),
        sa.Column('doctor_signature', sa.String(100)),
        sa.Column('ordered_at', sa.DateTime()),
        sa.Column('delivered_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # 按照依赖关系的逆序删除
    tcm_tables = ['tcm_delivery_orders', 'tcm_herbs', 'tcm_formula_library',
                  'tcm_formula_recommendations', 'tcm_syndrome_diagnoses',
                  'tongue_images', 'tcm_profiles']
    core_tables = ['pharmacogenomic_profiles', 'data_connections', 'prescriptions',
                   'medication_recommendations', 'diagnosis_results', 'health_records',
                   'health_observations', 'health_profiles', 'users']
    for table in tcm_tables + core_tables:
        op.drop_table(table)