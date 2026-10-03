"""
UTM 参数追踪中间件
自动从 URL 中提取 UTM 参数，关联到会话和用户注册来源
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger
import json


class UTMTrackerMiddleware(BaseHTTPMiddleware):
    """自动追踪 UTM 参数，存入 request.state 供后续注册/分析使用"""

    UTM_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract UTM params from query string
        utm_data = {}
        for param in self.UTM_PARAMS:
            value = request.query_params.get(param)
            if value:
                utm_data[param] = value[:200]  # Truncate long values

        # Store in request.state for downstream access
        if utm_data:
            request.state.utm_data = utm_data
            logger.debug(f"[UTM] Captured: {utm_data}")
        else:
            request.state.utm_data = {}

        # Also check for ref code (e.g., ?ref=abc123)
        ref_code = request.query_params.get("ref")
        if ref_code and "ref" not in utm_data:
            utm_data["ref"] = ref_code[:50]
            request.state.utm_data = utm_data

        response = await call_next(request)
        return response


def build_utm_url(base_url: str, source: str, medium: str, campaign: str = "", content: str = "") -> str:
    """构建带 UTM 参数的 URL"""
    from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

    parsed = urlparse(base_url)
    params = dict(parse_qsl(parsed.query))
    params.update({
        "utm_source": source,
        "utm_medium": medium,
    })
    if campaign:
        params["utm_campaign"] = campaign
    if content:
        params["utm_content"] = content

    return urlunparse(parsed._replace(query=urlencode(params)))
