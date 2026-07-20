# -*- coding: utf-8 -*-
"""认证相关 Schema"""

import re
from pydantic import BaseModel, EmailStr, field_validator


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
    """用户登录输入"""

    email: EmailStr
    password: str


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
