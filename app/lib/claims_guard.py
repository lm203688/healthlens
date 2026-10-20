"""Claims guard — FastAPI 端点级的 claims_engine 出口包裹器。

R3 fail-closed 落地后，所有面向用户的 wellness 端点都应经 `apply_claims`
包裹其 return 语句。任何 banned_term 命中立即 403 + 审计，不做降级放行。

设计要点：
- 独立于 `claims_engine.py`：claims_engine.py 保持"纯策略 + 纯扫描"，不引入
  FastAPI 依赖；本模块作为 API 层薄薄一层的 adapter。
- fail-closed：命中即 403，不返回任何 payload（避免"降级泄露"）。
- 法域解析：默认走 `get_user_jurisdiction(user)`（读 user.region/jurisdiction），
  缺失时回退 "cn"。
- 端点开关：`check_endpoint_allowed` 已在 policy 层实现，本模块**不重复**——
  需要端点级阻断的（如 EU 拒绝 diagnosis）在业务代码里显式调用 `check_endpoint_allowed`。

用法（每个端点末尾一行）：
    return apply_claims(payload, current_user, "/api/v1/xxx/yyy")
"""
from fastapi import HTTPException, status
from loguru import logger

from app.lib.claims_engine import (
    ClaimsPolicyError,
    filter_output,
    get_user_jurisdiction,
)


def apply_claims(
    payload: dict,
    user=None,
    endpoint: str = "",
    *,
    jurisdiction: str | None = None,
    status_code: int = status.HTTP_403_FORBIDDEN,
) -> dict:
    """按用户法域过滤输出，任一 banned_term 命中即 403。

    与 `claims_engine.filter_output` 的差别：本函数承担 API 层的错误语义，
    把 `ClaimsPolicyError` 翻译为 `HTTPException`，并写入统一的日志前缀。

    Args:
        payload: 端点准备返回的 dict。
        user: 当前用户对象（需含 `id` 与 `region` 或 `jurisdiction` 属性）。
              公开端点可传 None，此时法域由 `jurisdiction` 参数指定，
              缺失时回退 "cn"（首发市场）。
        endpoint: 端点路径（用于策略里 `endpoint_overrides` 匹配与审计）。
        jurisdiction: 显式指定法域（覆盖 user 属性）。公开端点用它。
        status_code: 违规时返回的 HTTP 状态码，默认 403。

    Returns:
        过滤后的 payload（可能被去掉越线字段 / 加免责声明）。

    Raises:
        HTTPException: 403，detail 含 violations 摘要与法域。
    """
    try:
        if jurisdiction:
            j = jurisdiction
        elif user is not None:
            j = get_user_jurisdiction(user)
        else:
            j = "cn"
        result = filter_output(payload, j, endpoint=endpoint)
        if result.violations or result.removed_fields:
            logger.warning(
                f"[Claims] endpoint={endpoint} user={getattr(user, 'id', '?')} "
                f"jurisdiction={j} violations={len(result.violations)} "
                f"removed={len(result.removed_fields)}"
            )
        return result.payload
    except ClaimsPolicyError as e:
        logger.warning(
            f"[Claims] BLOCKED endpoint={endpoint} "
            f"user={getattr(user, 'id', '?')}: {e}"
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "claims_policy_violation",
                "endpoint": endpoint,
                "message": str(e),
            },
        )
