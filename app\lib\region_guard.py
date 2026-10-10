"""区域数据驻留代码级约束

**核心命题**：区域驻留不能靠文档约束，必须靠代码拦截。
PII 跨越 region 边界读取或写入 → 立即抛异常。

**设计**：
- `get_current_region()` 从请求头 X-HL-Region 或环境变量读取当前请求区域
- `enforce_region_match(user, current_region)` 检查用户 region 与当前请求区域是否匹配
- `assert_same_region(record_region, user_region)` 记录级检查
- 所有违反返回 HTTPException 403，detail 包含 `data_residency_violation`

**约束范围**（当前已接入的端点）：
- 基因数据（genome.py）—— HGRAC 硬约束：中国遗传资源数据不得出境
- 诊断结果（diagnosis.py）—— 敏感 PI
- 健康观察数据（observations）—— 敏感 PI
- GDPR 数据导出/删除

**约束级别**：
- STRICT：所有敏感 PI 端点默认 strict
- 未来可扩展到"聚合回传"模式（仅脱敏统计，需单独同意）
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import HTTPException, status, Request

logger = logging.getLogger(__name__)


# 允许的 region 代码（与 app/models/user.py 保持一致）
VALID_REGIONS = {"cn", "sg", "eu", "us", "uk", "au", "default"}
DEFAULT_REGION = os.getenv("HL_DEPLOY_REGION", "cn")


class DataResidencyError(HTTPException):
    """数据驻留约束被违反时抛出的异常（继承 HTTPException，直接被 FastAPI 捕获）。"""

    def __init__(self, detail: str, user_region: str, requested_region: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "data_residency_violation",
                "user_region": user_region,
                "requested_region": requested_region,
                "message": detail,
                "docs": "https://healthlens.cc/docs/data-residency",
            },
        )


def get_request_region(request: Request) -> str:
    """从请求头或部署环境读取当前请求归属的区域。

    优先级：
    1. X-HL-Region 请求头（由边缘网关 / CDN 写入）
    2. 环境变量 HL_REQUEST_REGION（部署时按区域设置）
    3. 默认部署区域 HL_DEPLOY_REGION

    返回值：region 短码（cn/sg/eu/...）。
    """
    header_region = request.headers.get("x-hl-region")
    if header_region:
        r = header_region.strip().lower()
        if r in VALID_REGIONS:
            return r
    env_region = os.getenv("HL_REQUEST_REGION")
    if env_region:
        r = env_region.strip().lower()
        if r in VALID_REGIONS:
            return r
    return DEFAULT_REGION


def get_user_region(user) -> str:
    """从 User 对象提取 region 字段（缺失时默认 cn）。"""
    if user is None:
        return DEFAULT_REGION
    r = getattr(user, "region", None)
    if r:
        return str(r).lower()
    return DEFAULT_REGION


def enforce_region_match(
    user,
    request: Request,
    strict: bool = True,
) -> str:
    """强制检查用户 region 与当前请求 region 匹配。

    Args:
        user: 当前登录用户 ORM 对象
        request: FastAPI Request 对象
        strict: True 时不匹配直接 403；False 时仅记录 warning 不拦截

    Returns:
        当前用户 region

    Raises:
        DataResidencyError: strict=True 且 region 不匹配时抛出
    """
    user_region = get_user_region(user)
    request_region = get_request_region(request)

    if user_region != request_region:
        msg = (
            f"Data residency violation: user.region={user_region} "
            f"but request.region={request_region}. "
            f"PII cannot cross regional boundaries."
        )
        if strict:
            logger.warning(msg)
            raise DataResidencyError(msg, user_region, request_region)
        else:
            logger.warning(f"[Non-strict] {msg}")

    return user_region


def assert_same_region(
    record_region: str | None,
    user_region: str,
    entity_name: str = "record",
) -> None:
    """记录级驻留检查：数据记录的 region 必须与用户 region 一致。

    适用于读写具体记录时（如读取某条健康观察）。

    Raises:
        DataResidencyError: 不一致时抛出
    """
    if not record_region:
        return  # 无标记，跳过（向后兼容）
    record_r = str(record_region).lower()
    if record_r != user_region:
        raise DataResidencyError(
            f"{entity_name}.region={record_r} does not match user.region={user_region}",
            user_region=user_region,
            requested_region=record_r,
        )


# ── 便捷依赖注入：给 FastAPI 端点用 ──────────────────────────

def region_guard(request: Request):
    """依赖注入装饰器：返回当前请求 region。"""
    return get_request_region(request)


# ── 部署检查：启动时报告当前部署区域 ────────────────────────

def report_deployment_region() -> str:
    """返回当前部署所属区域（供启动日志使用）。"""
    return DEFAULT_REGION
