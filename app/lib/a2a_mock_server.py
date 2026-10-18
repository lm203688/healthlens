"""Local mock A2A agent server（stdlib-only）——用于 A2A 联邦 demo 与客户端测试。

**为什么需要它**：`app/api/a2a.py` 是 HealthLens 自己实现的 A2A server，
要真正证明 outbound 联邦（HealthLens 作为 client 调外部 agent）能跑通，
需要一个独立的"对方 agent"能接收 JSON-RPC 请求。生产环境对方会是真实的
第三方 A2A agent，本地 demo 用这个 mock 就能闭环。

**设计约束**：
- 只依赖 stdlib（`http.server` + `json`），不需要 uvicorn/fastapi 起第二进程
- 完整支持 A2A v1.0.1 的 SendMessage / ListTasks / GetTask / CancelTask
- 用一个可复用的 handler callable 抽象核心逻辑，方便 pytest 直接函数式调用
  （不需要真的启 HTTP 服务）

**协议对齐**：与 `app/api/a2a.py` 保持错误码/字段名/状态机一致。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-18)
"""
from __future__ import annotations

import http.server
import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────────── 错误码（与 app/api/a2a.py 一致） ───────────────────────────

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
A2A_TASK_NOT_FOUND = -32001
A2A_INVALID_TRANSITION = -32002


# ─────────────────────────── 内存 Task 存储（mock 版） ───────────────────────────

@dataclass
class _MockTask:
    task_id: str
    context_id: str
    status: str = "SUBMITTED"
    status_message: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "contextId": self.context_id,
            "status": {
                "state": self.status,
                "message": self.status_message,
            },
            "artifacts": self.artifacts,
            "history": self.history,
        }


class MockTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, _MockTask] = {}
        self._lock = threading.Lock()

    def create(self, task_id: str | None, context_id: str | None,
               status_message: str | None = None) -> _MockTask:
        tid = task_id or f"task-{uuid.uuid4().hex[:12]}"
        ctx = context_id or f"ctx-{uuid.uuid4().hex[:8]}"
        with self._lock:
            task = _MockTask(task_id=tid, context_id=ctx, status_message=status_message)
            task.history.append({"kind": "status", "status": {"state": "SUBMITTED"}})
            self._tasks[tid] = task
            return task

    def get(self, task_id: str) -> _MockTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self, context_id: str | None = None, status: str | None = None,
             limit: int = 50) -> list[_MockTask]:
        with self._lock:
            out = list(self._tasks.values())
        if context_id:
            out = [t for t in out if t.context_id == context_id]
        if status:
            out = [t for t in out if t.status == status]
        return out[: min(limit, 50)]

    def update_status(self, task_id: str, new_status: str,
                      status_message: str | None = None) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if t is None:
                raise KeyError(task_id)
            t.status = new_status
            t.status_message = status_message
            t.history.append({"kind": "status",
                               "status": {"state": new_status, "message": status_message}})

    def add_artifact(self, task_id: str, artifact: dict[str, Any]) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if t is None:
                raise KeyError(task_id)
            t.artifacts.append(artifact)
            t.history.append({"kind": "artifact", **artifact})


# ─────────────────────────── 消息处理（纯函数） ───────────────────────────

def handle_jsonrpc(
    body: dict[str, Any],
    store: MockTaskStore,
    *,
    responder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """处理一次 JSON-RPC 请求，返回响应 envelope。

    Args:
        body: 请求 body
        store: 内存 task 存储
        responder: 可选回调，收到 SendMessage 时用它生成 artifact。
                   签名 (message) -> artifact_data_dict。默认回显 message.text。
    """
    def err(req_id: Any, code: int, msg: str, data: Any = None) -> dict[str, Any]:
        e: dict[str, Any] = {"code": code, "message": msg}
        if data is not None:
            e["data"] = data
        return {"jsonrpc": "2.0", "error": e, "id": req_id}

    def ok(req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    if not isinstance(body, dict):
        return err(None, JSONRPC_INVALID_REQUEST, "body must be object")
    if body.get("jsonrpc") != "2.0":
        return err(body.get("id"), JSONRPC_INVALID_REQUEST, "jsonrpc must be '2.0'")
    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params")

    if not isinstance(method, str):
        return err(req_id, JSONRPC_INVALID_REQUEST, "method must be string")

    # --- SendMessage ---
    if method == "SendMessage":
        if not isinstance(params, dict):
            return err(req_id, JSONRPC_INVALID_PARAMS, "params must be object")
        message = params.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("parts"), list):
            return err(req_id, JSONRPC_INVALID_PARAMS, "message.parts must be list")

        task = store.create(
            task_id=params.get("taskId"),
            context_id=params.get("contextId") or message.get("contextId"),
            status_message=params.get("statusMessage"),
        )
        store.update_status(task.task_id, "WORKING")

        # Generate artifact via responder (default: echo first text part)
        if responder is not None:
            try:
                artifact_data = responder(message)
            except Exception as exc:  # noqa: BLE001
                artifact_data = {"error": str(exc)}
        else:
            text_bits = [
                p.get("text", "") for p in message.get("parts", [])
                if isinstance(p, dict) and isinstance(p.get("text"), str)
            ]
            artifact_data = {"echo": " ".join(text_bits).strip()}

        artifact = {
            "artifactId": f"artifact-{task.task_id}",
            "parts": [{"kind": "data", "data": artifact_data}],
            "name": "mock_response",
        }
        store.add_artifact(task.task_id, artifact)
        store.update_status(task.task_id, "COMPLETED", status_message="ok")
        return ok(req_id, store.get(task.task_id).to_dict())

    # --- GetTask ---
    if method == "GetTask":
        if not isinstance(params, dict):
            return err(req_id, JSONRPC_INVALID_PARAMS, "params must be object")
        tid = params.get("taskId")
        if not isinstance(tid, str) or not tid:
            return err(req_id, JSONRPC_INVALID_PARAMS, "taskId must be string")
        task = store.get(tid)
        if task is None:
            return err(req_id, A2A_TASK_NOT_FOUND, "task not found")
        return ok(req_id, task.to_dict())

    # --- ListTasks ---
    if method == "ListTasks":
        if not isinstance(params, dict):
            return err(req_id, JSONRPC_INVALID_PARAMS, "params must be object")
        try:
            limit = int(params.get("limit", 50))
        except (TypeError, ValueError):
            return err(req_id, JSONRPC_INVALID_PARAMS, "limit must be int")
        tasks = store.list(
            context_id=params.get("contextId"),
            status=params.get("status"),
            limit=limit,
        )
        return ok(req_id, {
            "tasks": [t.to_dict() for t in tasks],
            "totalCount": len(tasks),
        })

    # --- CancelTask ---
    if method == "CancelTask":
        if not isinstance(params, dict):
            return err(req_id, JSONRPC_INVALID_PARAMS, "params must be object")
        tid = params.get("taskId")
        if not isinstance(tid, str) or not tid:
            return err(req_id, JSONRPC_INVALID_PARAMS, "taskId must be string")
        task = store.get(tid)
        if task is None:
            return err(req_id, A2A_TASK_NOT_FOUND, "task not found")
        if task.status in {"COMPLETED", "FAILED", "CANCELED"}:
            return err(req_id, A2A_INVALID_TRANSITION, "task already terminal")
        store.update_status(task.task_id, "CANCELED",
                            status_message=params.get("reason"))
        return ok(req_id, store.get(tid).to_dict())

    # --- unknown ---
    return err(req_id, JSONRPC_METHOD_NOT_FOUND, f"unknown method: {method}")


# ─────────────────────────── HTTP Server 包装 ───────────────────────────

class MockA2AHandler(http.server.BaseHTTPRequestHandler):
    """stdlib HTTP handler；POST /a2a 走 handle_jsonrpc。"""

    # Class-level injection points（由 MockA2AServer 设置）
    store: MockTaskStore = MockTaskStore()
    responder: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/a2a":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        resp = handle_jsonrpc(body, self.store, responder=self.responder)
        payload = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # 静默，避免测试输出被 server log 淹没
        pass


class MockA2AServer:
    """在后台线程起一个 mock A2A agent，`start()` 后返回 url，`stop()` 清理。

    用法（context manager 更清晰）：
        with MockA2AServer() as srv:
            url = srv.url
            client = A2AClient(url)
            client.send_message(...)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 responder: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self._host = host
        self._port = port
        self._responder = responder
        self.store = MockTaskStore()
        self._httpd: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._httpd is None:
            return ""
        return f"http://{self._host}:{self._httpd.server_port}"

    def start(self) -> str:
        # 关键坑（2026-10-18 踩出）：把普通函数作为类属性挂到 handler 类上，
        # Python 的描述符协议会在实例访问时自动绑定 self，导致
        # `self.responder(message)` 变成 `self.responder(handler_self, message)`
        # ——两个位置参数，触发 "takes 1 positional argument but 2 were given"。
        # 用 staticmethod 包裹可以保留纯函数的调用签名。
        handler_attrs: dict[str, Any] = {"store": self.store}
        if self._responder is not None:
            handler_attrs["responder"] = staticmethod(self._responder)
        handler = type("_BoundHandler", (MockA2AHandler,), handler_attrs)
        self._httpd = http.server.HTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                         name="mock-a2a-server", daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def __enter__(self) -> "MockA2AServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


__all__ = [
    "MockA2AServer",
    "MockA2AHandler",
    "MockTaskStore",
    "handle_jsonrpc",
    "JSONRPC_PARSE_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INTERNAL_ERROR",
    "A2A_TASK_NOT_FOUND",
    "A2A_INVALID_TRANSITION",
]
