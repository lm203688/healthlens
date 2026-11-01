# -*- coding: utf-8 -*-
"""认证相关 Schema"""

import re
from pydantic import BaseModel, EmailStr, field_validator, model_validator


PASSWORD_MIN_LENGTH = 8


def _validate_password_strength(password: str) -> str:
    """密码强度校验: 至少8位, 包含字母和数字"""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    return password


class RegisterInput(BaseModel):
    """用户注册输入"""

    email: EmailStr
    password: str
    phone: str | None = None
    name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # 中国手机号格式: 1开头的11位数字
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid Chinese phone number format (expected 1[3-9]XXXXXXXXX)")
        return v


class LoginInput(BaseModel):
    """用户登录输入（支持邮箱或手机号）"""

    account: str  # 邮箱或手机号
    password: str

    @field_validator("account")
    @classmethod
    def validate_account(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("请输入邮箱或手机号")
        if "@" in v:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                raise ValueError("邮箱格式不正确")
        else:
            if not re.match(r"^1[3-9]\d{9}$", v):
                raise ValueError("手机号格式不正确（应为 1[3-9] 开头的 11 位号码）")
        return v


class OtpSendInput(BaseModel):
    """获取验证码输入（手机号或邮箱，登录与注册合一）"""

    account: str

    @field_validator("account")
    @classmethod
    def validate_account(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("请输入手机号或邮箱")
        if "@" in v:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                raise ValueError("邮箱格式不正确")
        else:
            if not re.match(r"^1[3-9]\d{9}$", v):
                raise ValueError("手机号格式不正确（应为 1[3-9] 开头的 11 位号码）")
        return v


class OtpVerifyInput(BaseModel):
    """验证码校验输入"""

    account: str
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("验证码应为数字")
        return v


class RefreshInput(BaseModel):
    """刷新 Token 输入"""

    refresh_token: str


class TokenOutput(BaseModel):
    """Token 输出"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOutput(BaseModel):
    """用户信息输出"""

    id: str
    email: str
    phone: str | None
    role: str
    created_at: str


class RoleUpdateInput(BaseModel):
    """角色更新输入 (仅 admin 可调用)"""

    user_id: str
    role: str  # "patient" | "doctor" | "admin"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"patient", "doctor", "admin"}
        if v not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v


class TotpEnrollInput(BaseModel):
    """TOTP 注册输入（用户绑定认证器 App）"""

    pass  # 无需额外字段，由服务端生成密钥


class TotpVerifyInput(BaseModel):
    """TOTP 验证码校验输入（第二因素：需先通过 /totp/challenge 拿到一次性挑战）"""

    challenge: str  # 第一因素校验后签发的一次性短时挑战
    code: str  # 6 位数字

    @field_validator("challenge")
    @classmethod
    def validate_challenge(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("请先完成第一因素校验")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = (v or "").strip().replace(" ", "")
        if not v.isdigit() or len(v) != 6:
            raise ValueError("验证码应为 6 位数字")
        return v


class TotpConfirmInput(BaseModel):
    """TOTP 注册确认输入（仅含 6 位码，不需要 challenge——这是绑定流程不是登录）"""

    code: str  # 6 位数字

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = (v or "").strip().replace(" ", "")
        if not v.isdigit() or len(v) != 6:
            raise ValueError("验证码应为 6 位数字")
        return v


class TotpChallengeInput(BaseModel):
    """TOTP 第二因素挑战输入：账号 + 第一因素（密码 或 短信/邮件验证码）"""

    account: str  # 邮箱或手机号
    password: str | None = None  # 密码通道的第一因素
    otp_code: str | None = None  # 短信/邮件验证码通道的第一因素

    @field_validator("account")
    @classmethod
    def validate_account(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("请输入邮箱或手机号")
        if "@" in v:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                raise ValueError("邮箱格式不正确")
        else:
            if not re.match(r"^1[3-9]\d{9}$", v):
                raise ValueError("手机号格式不正确（应为 1[3-9] 开头的 11 位号码）")
        return v

    @model_validator(mode="after")
    def _validate_first_factor(self):
        if not self.password and not self.otp_code:
            raise ValueError("请提供密码或短信验证码作为第一因素")
        return self


class TotpChallengeOutput(BaseModel):
    """TOTP 挑战签发输出"""

    challenge: str
    expires_in: int  # 挑战有效期（秒）
    method: str  # 第一因素使用的通道（password | otp）
    requires_totp: bool  # 该账号是否启用了 TOTP


class JurisdictionUpdateInput(BaseModel):
    """用户法域更新输入"""

    jurisdiction: str

    @field_validator("jurisdiction")
    @classmethod
    def validate_jurisdiction(cls, v: str) -> str:
        v = (v or "").strip().lower()
        allowed = {"cn", "us", "uk", "au", "eu"}
        if v not in allowed:
            raise ValueError(f"jurisdiction must be one of {allowed}")
        return v


class TotpStatusOutput(BaseModel):
    """TOTP 状态输出"""

    enabled: bool
    provisioning_uri: str | None = None  # enrollment 时返回，供前端渲染二维码
    account: str | None = None

