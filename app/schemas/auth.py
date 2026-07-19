# -*- coding: utf-8 -*-
"""认证相关 Schema"""

from pydantic import BaseModel, EmailStr


class RegisterInput(BaseModel):
    """用户注册输入"""

    email: EmailStr
    password: str
    phone: str | None = None


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
