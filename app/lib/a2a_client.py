"""A2A v1.0.1 JSON-RPC 客户端（用于跨 agent 互操作）。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「A2A v1.0.1 SendMessage / ListTasks / GetTask / CancelTask」。

定位：
- **outbound 侧**：`app/api/a2a.py` 是入站（HealthLens 作为 A2A **server** 被外部
  agent 调用）；本模块是出站（HealthLens 作为 A2A **client** 调用外部 agent）。
- **单依赖 stdlib**：只用 `urllib.request`，不引入 httpx/requests，保持
  healthlens_agent 的 stdlib-only 特性。
- **thin wrapper**：只做 JSON-RPC envelope 打包 + 超时/错误处理；不缓存、
  不做重试（上层负责重试策略），不持久化（TaskStore 已有）。

协议约束（严格对齐 A2A v1.0.1 spec）：
- HTTP method：POST，Content-Type: application/json
- 请求体：`{"jsonrpc":"2.0","method":"<verb>","params":{...},"id":...}`
- 响应体：`{"jsonrpc":"2.0","result":{...},"id":...}` 或
         `{"jsonrpc":"2.0","error":{"code":...,"message":...},"id":...}`
- HTTP 状态码 200 表示 JSON-RPC 层已处理（含协议内 error）；
  HTTP 400 表示 body 不是合法 JSON。
- 方法集合：`{"SendMessage","ListTasks","GetTask","CancelTask"}`。
- JWS 签名 optional：如果 `auth_jws` 参数非空，会加 `Authorization: Bearer <jws>`。

失败语义（fail-loud）：
- 超时抛 `A2AClientTimeoutError`
- HTTP 非 200/400 抛 `A2AClientHTTPError`
- JSON-RPC error envelope 抛 `A2AJsonRpcError`（含 code/message/data）
- body 非 JSON / 非 object 抛 `A2AClientProtocolError`

生产部署提示：本客户端可安全用于生产 outbound 调用（stdlib、同步、可
线程化）。如果需要异步，用 `httpx.AsyncClient` 替换 `_post_jsonrpc` 即可。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-18)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request


# ─────────────────────────── 错误类型 ───────────────────────────

class A2AClientError(Exception):
    """A2A 客户端错误基类。"""


class A2AClientTimeoutError(A2AClientError):
    """HTTP 请求超时。"""


class A2AClientHTTPError(A2AClientError):
    """HTTP 非 200 状态码。"""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


class A2AClientProtocolError(A2AClientError):
    """响应 body 不是合法 JSON / JSON-RPC envelope。"""


class A2AJsonRpcError(A2AClientError):
    """JSON-RPC error envelope 已收到（协议内错误）。"""

    def __init__(self, code: int, message: str, data: Any = None, req_id: Any = None):
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data
        self.id = req_id


# ─────────────────────────── 已知方法与错误码 ───────────────────────────

SUPPORTED_METHODS: frozenset[str] = frozenset(
    {"SendMessage", "ListTasks", "GetTask", "CancelTask"}
)

# 与 app/api/a2a.py 保持同步
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
A2A_TASK_NOT_FOUND = -32001
A2A_INVALID_TRANSITION = -32002
A2A_AUTHENTICATION_REQUIRED = -32003


# ─────────────────────────── 核心客户端 ───────────────────────────

class A2AClient:
    """Minimal synchronous A2A JSON-RPC 2.0 client (stdlib only).

    Args:
        base_url: 目标 A2A agent 的端点 URL。可以是完整 URL（含 `/a2a` 后缀）
                  或仅 base（如 `http://localhost:8123`），二者均可。
        timeout_s: 单请求超时秒数，默认 30。
        auth_jws: 可选 Bearer JWS，非空时自动加 `Authorization` header。
        default_headers: 额外 headers（如 `X-Protocol-Version: 1.0.1`）。
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 30.0,
        auth_jws: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be non-empty")
        # 归一化：允许 `.../a2a` 或 `.../`
        self._url = base_url.rstrip("/")
        if not self._url.endswith("/a2a"):
            self._url = self._url + "/a2a"
        self._timeout = float(timeout_s)
        self._auth_jws = auth_jws
        self._default_headers = dict(default_headers or {})

    # -- Public methods --------------------------------------------------

    def send_message(
        self,
        *,
        message: dict[str, Any],
        context_id: str | None = None,
        task_id: str | None = None,
        status_message: str | None = None,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        """SendMessage：创建 task 并同步返回（含 artifact 和 COMPLETED 状态）。"""
        params: dict[str, Any] = {"message": message}
        if context_id is not None:
            params["contextId"] = context_id
        if task_id is not None:
            params["taskId"] = task_id
        if status_message is not None:
            params["statusMessage"] = status_message
        return self._call("SendMessage", params, req_id=req_id)

    def list_tasks(
        self,
        *,
        context_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        """ListTasks：按 contextId / status 过滤任务列表。"""
        params: dict[str, Any] = {"limit": int(limit)}
        if context_id is not None:
            params["contextId"] = context_id
        if status is not None:
            params["status"] = status
        return self._call("ListTasks", params, req_id=req_id)

    def get_task(self, task_id: str, *, req_id: str | None = None) -> dict[str, Any]:
        """GetTask：按 taskId 拿完整任务（含 artifact）。"""
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id must be a non-empty string")
        return self._call("GetTask", {"taskId": task_id}, req_id=req_id)

    def cancel_task(
        self,
        task_id: str,
        *,
        reason: str | None = None,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        """CancelTask：仅允许从 SUBMITTED / WORKING 状态出发。"""
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id must be a non-empty string")
        params: dict[str, Any] = {"taskId": task_id}
        if reason is not None:
            params["reason"] = reason
        return self._call("CancelTask", params, req_id=req_id)

    # -- Internals -------------------------------------------------------

    def _call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        if method not in SUPPORTED_METHODS:
            raise ValueError(f"unknown method: {method}")
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id or _new_id(),
        }
        resp = self._post_jsonrpc(body)

        # Envelope 结构校验
        if not isinstance(resp, dict):
            raise A2AClientProtocolError(f"response must be JSON object, got {type(resp).__name__}")
        if resp.get("jsonrpc") != "2.0":
            raise A2AClientProtocolError("response missing jsonrpc='2.0' field")

        if "error" in resp and isinstance(resp["error"], dict):
            err = resp["error"]
            code = int(err.get("code", JSONRPC_INTERNAL_ERROR))
            msg = str(err.get("message", "unknown error"))
            data = err.get("data")
            raise A2AJsonRpcError(code=code, message=msg, data=data,
                                   req_id=resp.get("id"))

        if "result" not in resp:
            raise A2AClientProtocolError("response has neither 'result' nor 'error'")
        return resp["result"]

    def _post_jsonrpc(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "healthlens-a2a-client/1.0",
            **self._default_headers,
        }
        if self._auth_jws:
            headers["Authorization"] = f"Bearer {self._auth_jws}"

        req = urllib_request.Request(
            self._url, data=payload, method="POST", headers=headers,
        )
        try:
            with urllib_request.urlopen(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", resp.getcode())
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib_error.HTTPError as exc:
            body_txt = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise A2AClientHTTPError(status=exc.code, body=body_txt) from exc
        except urllib_error.URLError as exc:
            raise A2AClientTimeoutError(f"connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise A2AClientTimeoutError(f"timed out after {self._timeout}s") from exc

        if status != 200:
            raise A2AClientHTTPError(status=status, body=raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise A2AClientProtocolError(f"response body is not valid JSON: {exc}") from exc


def _new_id() -> str:
    """JSON-RPC id：短 UUID（协议允许 string）。"""
    return uuid.uuid4().hex[:16]


__all__ = [
    "A2AClient",
    "A2AClientError",
    "A2AClientTimeoutError",
    "A2AClientHTTPError",
    "A2AClientProtocolError",
    "A2AJsonRpcError",
    "SUPPORTED_METHODS",
    "JSONRPC_PARSE_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INTERNAL_ERROR",
    "A2A_TASK_NOT_FOUND",
    "A2A_INVALID_TRANSITION",
    "A2A_AUTHENTICATION_REQUIRED",
]
