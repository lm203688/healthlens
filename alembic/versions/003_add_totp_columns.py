"""为 users 表添加 TOTP 列

Revision ID: 003_add_totp_columns
Revises: 002_add_missing_tables
Create Date: 2026-09-20

新增三列支持零成本 TOTP 认证器通道：
- totp_secret: base32 编码密钥，nullable（未注册时为 NULL）
- totp_enabled: 是否启用 TOTP
- otp_method: 首选验证码通道 (otp/totp)
"""
from alembic import op
import sqlalchemy as sa


revision = '003_add_totp_columns'
down_revision = '002_add_missing_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TOTP 密钥（base32，最长 32 字符，留 64 字节余量）
    op.add_column('users', sa.Column('totp_secret', sa.String(64), nullable=True))
    # TOTP 开关
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean, server_default='false'))
    # 首选 OTP 通道: otp (短信/邮件) / totp (认证器 App)
    op.add_column('users', sa.Column('otp_method', sa.String(10), server_default='otp'))


def downgrade() -> None:
    op.drop_column('users', 'otp_method')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
