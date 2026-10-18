"""请求 ID 中间件 - 为每个请求生成唯一 ID 用于追踪"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """生成或透传 X-Request-ID, 注入响应头"""

    async def dispatch(self, request: Request, call_next):
        # 优先从请求头获取, 否则生成新的
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # 存储到 request.state 供后续使用
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
