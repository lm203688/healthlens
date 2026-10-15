"""HealthLensClient — 异步 Python 客户端（Powered-by SDK）。

设计要点
--------
- 使用 httpx.AsyncClient，支持作为 async context manager 或直接实例化
- 认证：传入 api_key 时默认走 `X-API-Key`；也支持 bearer_token（预留多协议）
- 非 2xx 一律 fail-loud：抛 HealthLensAPIError（含 status_code / detail）；
  401/403 抛更细的 HealthLensAuthError
- 所有端点返回 dict（合作方拿到的原始 JSON 响应体，未做额外加工）
- wellness 边界：所有端点响应已带 disclaimer，本 client 不修改字段

不写真实外部调用逻辑：调用逻辑仅为薄封装 httpx，测试通过 mock /
ASGITransport 打桩，不依赖任何外部网络。
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.version import __version__ as _VERSION


class HealthLensAPIError(RuntimeError):
    """非 2xx 响应抛出的通用异常。

    Attributes:
        status_code: HTTP 状态码
        detail: 响应体中的 detail / error 字段（原样保留，供上游日志）
        response: httpx.Response 实例（可能已被消费，谨慎复用）
    """

    def __init__(self, status_code: int, detail: Any, response: httpx.Response | None = None):
        self.status_code = status_code
        self.detail = detail
        self.response = response
        msg = f"HealthLens API error: HTTP {status_code} — {detail}"
        super().__init__(msg)


class HealthLensAuthError(HealthLensAPIError):
    """401 / 403 —— 认证/授权失败。"""


class HealthLensClient:
    """异步客户端。

    Args:
        base_url: HealthLens API 根路径，如 ``https://api.healthlens.cc``。
            末尾的 ``/`` 会被去掉，避免双重斜杠。
        api_key: 合作方 API Key（推荐）。走 ``X-API-Key`` header。
        bearer_token: 可选的 Bearer Token（预留，未来支持 OAuth 场景）。
        timeout: 单次请求超时（秒），默认 30s。
        headers: 附加请求头（如合作方自定义 trace-id）。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        bearer_token: str | None = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not isinstance(base_url, str):
            raise ValueError("base_url 不能为空")
        self.base_url = base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("base_url 去除尾部斜杠后为空")
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout = timeout

        default_headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Client": f"healthlens-sdk-python/{_VERSION}",
        }
        if api_key:
            default_headers["X-API-Key"] = api_key
        if bearer_token:
            default_headers["Authorization"] = f"Bearer {bearer_token}"
        if headers:
            default_headers.update(headers)

        kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": timeout,
            "headers": default_headers,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**kwargs)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "HealthLensClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # 底层请求
    # ------------------------------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        # path 统一带前导 "/"
        if not path.startswith("/"):
            path = "/" + path
        resp = await self._client.request(
            method, path, json=json, params=params, headers=headers
        )
        return self._handle(resp)

    @staticmethod
    def _handle(resp: httpx.Response) -> dict:
        """统一错误处理：非 2xx fail-loud，2xx 返回 JSON dict。"""
        if not (200 <= resp.status_code < 300):
            try:
                detail = resp.json()
            except Exception:  # noqa: BLE001 - body 非 JSON 时保留原文
                detail = resp.text
            if resp.status_code in (401, 403):
                raise HealthLensAuthError(resp.status_code, detail, resp)
            raise HealthLensAPIError(resp.status_code, detail, resp)
        try:
            return resp.json()
        except Exception:  # noqa: BLE001 - 2xx 但非 JSON：fail-loud，返回空 dict 由上层判
            return {"success": False, "error": "non-JSON response from HealthLens API"}

    # ------------------------------------------------------------------
    # Partner-facing 端点
    # ------------------------------------------------------------------
    async def health_check(self) -> dict:
        """GET /partner-api/health —— 公开健康检查（无需 key）。"""
        return await self._request("GET", "/partner-api/health")

    async def config(self, partner_id: str) -> dict:
        """GET /partner-api/config —— 获取合作方配置（需 key）。"""
        return await self._request("GET", "/partner-api/config", params={"partner_id": partner_id})

    async def health_score(self, user_id: str, date: str | None = None) -> dict:
        """POST /partner-api/health-score —— 用户健康评分（需 key）。"""
        body: dict[str, Any] = {"user_id": user_id}
        if date:
            body["date"] = date
        return await self._request("POST", "/partner-api/health-score", json=body)

    async def axis_assessment(self, user_id: str) -> dict:
        """POST /partner-api/axis-assessment —— 八轴评估（需 key）。"""
        return await self._request("POST", "/partner-api/axis-assessment", json={"user_id": user_id})

    async def tcm_recommendations(self, user_id: str) -> dict:
        """POST /partner-api/tcm-recommendations —— TCM 推荐（需 key）。"""
        return await self._request("POST", "/partner-api/tcm-recommendations", json={"user_id": user_id})

    async def wellness_report(self, user_id: str) -> dict:
        """POST /partner-api/wellness-report —— 综合 wellness 报告（需 key）。"""
        return await self._request("POST", "/partner-api/wellness-report", json={"user_id": user_id})
