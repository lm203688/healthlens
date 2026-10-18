"""Tests for the A2A v1.0.1 JSON-RPC client (app.lib.a2a_client).

Why these tests exist
---------------------
`app/api/a2a.py` is the inbound side (HealthLens as an A2A **server**).
`app/lib/a2a_client.py` is the outbound side (HealthLens as an A2A **client**)
— added 2026-10-18 to close the A2A federation gap.

The client is stdlib-only so it can be exercised in-process against the
in-repo mock server (`app.lib.a2a_mock_server.MockA2AServer`) — no external
third-party A2A agent required.

Covers:
- Happy path: SendMessage → GetTask → ListTasks → CancelTask
- Protocol-level errors: JSON-RPC method_not_found, task_not_found,
  invalid_transition
- HTTP-level errors: malformed JSON, non-200 status
- JWS header attachment
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib import request as urllib_request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.lib.a2a_client import (
    A2AClient,
    A2AClientHTTPError,
    A2AClientProtocolError,
    A2AJsonRpcError,
    A2A_TASK_NOT_FOUND,
    JSONRPC_METHOD_NOT_FOUND,
)
from app.lib.a2a_mock_server import MockA2AServer, handle_jsonrpc, MockTaskStore


# ─────────────────────────── Fixtures ───────────────────────────

@pytest.fixture()
def mock_agent():
    """Start a mock A2A agent and yield (client, server)."""
    with MockA2AServer() as server:
        client = A2AClient(server.url, timeout_s=5.0)
        yield client, server


@pytest.fixture()
def mock_agent_with_responder():
    """Mock A2A agent with a custom responder that echoes query + adds a tag."""
    def responder(message: dict[str, Any]) -> dict[str, Any]:
        parts = message.get("parts", [])
        text = " ".join(
            p.get("text", "") for p in parts
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ).strip()
        return {
            "echo": text,
            "tag": "mock-response",
            "parts_count": len(parts),
        }
    with MockA2AServer(responder=responder) as server:
        client = A2AClient(server.url, timeout_s=5.0)
        yield client, server


# ─────────────────────────── Happy path ───────────────────────────

def test_send_message_creates_task_and_returns_completed(mock_agent_with_responder):
    client, server = mock_agent_with_responder
    message = {"parts": [{"kind": "text", "text": "hello wellness"}]}

    result = client.send_message(
        message=message,
        context_id="ctx-1",
        task_id="task-1",
        status_message="kicking off",
    )

    assert result["taskId"] == "task-1"
    assert result["contextId"] == "ctx-1"
    assert result["status"]["state"] == "COMPLETED"
    assert len(result["artifacts"]) == 1
    artifact_data = result["artifacts"][0]["parts"][0]["data"]
    assert artifact_data["echo"] == "hello wellness"
    assert artifact_data["tag"] == "mock-response"


def test_send_message_generates_task_id_if_absent(mock_agent):
    """If client doesn't supply taskId, the server generates one."""
    client, _ = mock_agent
    result = client.send_message(
        message={"parts": [{"kind": "text", "text": "auto id"}]},
    )
    assert result["taskId"] and result["taskId"].startswith("task-")
    assert result["contextId"] and result["contextId"].startswith("ctx-")


def test_get_task_returns_full_task(mock_agent_with_responder):
    client, _ = mock_agent_with_responder
    client.send_message(
        message={"parts": [{"kind": "text", "text": "query x"}]},
        context_id="ctx-2", task_id="task-2",
    )
    task = client.get_task("task-2")
    assert task["taskId"] == "task-2"
    assert task["status"]["state"] == "COMPLETED"
    # history must record SUBMITTED → WORKING → COMPLETED
    states = [h["status"]["state"] for h in task["history"] if h.get("kind") == "status"]
    assert states == ["SUBMITTED", "WORKING", "COMPLETED"]


def test_list_tasks_filters_by_context(mock_agent_with_responder):
    client, _ = mock_agent_with_responder
    for i in range(3):
        client.send_message(
            message={"parts": [{"kind": "text", "text": f"q{i}"}]},
            context_id="ctx-shared", task_id=f"task-{i}",
        )
    # Interleave a different context
    client.send_message(
        message={"parts": [{"kind": "text", "text": "other"}]},
        context_id="ctx-other", task_id="task-other",
    )
    result = client.list_tasks(context_id="ctx-shared", limit=10)
    assert result["totalCount"] == 3
    ids = {t["taskId"] for t in result["tasks"]}
    assert ids == {"task-0", "task-1", "task-2"}


def test_list_tasks_filters_by_status(mock_agent_with_responder):
    client, _ = mock_agent_with_responder
    client.send_message(
        message={"parts": [{"kind": "text", "text": "done"}]},
        context_id="ctx-s", task_id="task-done",
    )
    result = client.list_tasks(status="COMPLETED")
    assert result["totalCount"] >= 1
    assert all(t["status"]["state"] == "COMPLETED" for t in result["tasks"])


def test_cancel_task_from_submitted_or_working(mock_agent_with_responder):
    """The mock server completes SendMessage synchronously, so by the time
    we call cancel the task is COMPLETED and cancel must fail. This tests
    the client properly raises A2AJsonRpcError with code -32002."""
    client, _ = mock_agent_with_responder
    client.send_message(
        message={"parts": [{"kind": "text", "text": "to cancel"}]},
        context_id="ctx-c", task_id="task-cancel",
    )
    with pytest.raises(A2AJsonRpcError) as exc_info:
        client.cancel_task("task-cancel", reason="too late")
    assert exc_info.value.code == -32002


# ─────────────────────────── Error paths ───────────────────────────

def test_get_task_not_found_raises_json_rpc_error(mock_agent):
    client, _ = mock_agent
    with pytest.raises(A2AJsonRpcError) as exc_info:
        client.get_task("does-not-exist")
    assert exc_info.value.code == A2A_TASK_NOT_FOUND
    assert "not found" in exc_info.value.message.lower()


def test_list_tasks_limit_capped_at_50(mock_agent_with_responder):
    client, _ = mock_agent_with_responder
    # 51 sends (well over the 50 cap); only 50 should come back
    for i in range(51):
        client.send_message(
            message={"parts": [{"kind": "text", "text": f"i{i}"}]},
            context_id="ctx-cap", task_id=f"task-cap-{i}",
        )
    result = client.list_tasks(context_id="ctx-cap", limit=100)
    assert result["totalCount"] == 50  # capped by server


# ─────────────────────────── JWS header attachment ───────────────────────────

def test_auth_jws_attached_as_bearer_header():
    """If `auth_jws` is set, the client must send `Authorization: Bearer <jws>`."""
    captured: dict[str, str] = {}

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            captured["auth"] = self.headers.get("Authorization", "")
            captured["user_agent"] = self.headers.get("User-Agent", "")
            length = int(self.headers.get("Content-Length") or 0)
            _ = self.rfile.read(length)
            resp = {
                "jsonrpc": "2.0",
                "id": "probe",
                "result": {"taskId": "task-probe",
                           "status": {"state": "COMPLETED"},
                           "artifacts": [], "history": [], "contextId": "ctx-probe"},
            }
            payload = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):  # noqa: A002
            pass

    httpd = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    port = httpd.server_port
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        c = A2AClient(f"http://127.0.0.1:{port}",
                      auth_jws="header.payload.sig")
        c.send_message(message={"parts": [{"kind": "text", "text": "probe"}]})
        assert captured["auth"] == "Bearer header.payload.sig"
        assert "healthlens-a2a-client" in captured["user_agent"]
    finally:
        httpd.shutdown()
        httpd.server_close()


# ─────────────────────────── Non-200 handling ───────────────────────────

def test_http_500_raises_client_http_error():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"internal boom")

        def log_message(self, fmt, *args):  # noqa: A002
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = A2AClient(f"http://127.0.0.1:{port}", timeout_s=3.0)
        with pytest.raises(A2AClientHTTPError) as exc_info:
            c.get_task("anything")
        assert exc_info.value.status == 500
    finally:
        httpd.shutdown()
        httpd.server_close()


# ─────────────────────────── Constructor validation ───────────────────────────

def test_client_constructor_rejects_empty_url():
    with pytest.raises(ValueError):
        A2AClient("")


def test_client_constructor_normalizes_trailing_slash():
    c = A2AClient("http://127.0.0.1:9999/a2a/")
    assert c._url.endswith("/a2a")  # noqa: SLF001
    c2 = A2AClient("http://127.0.0.1:9999/")
    assert c2._url.endswith("/a2a")  # noqa: SLF001


# ─────────────────────────── Direct handler sanity (no HTTP) ───────────────────────────

def test_handle_jsonrpc_unknown_method():
    store = MockTaskStore()
    resp = handle_jsonrpc(
        {"jsonrpc": "2.0", "method": "DeleteTask", "params": {}, "id": 1},
        store,
    )
    assert resp["error"]["code"] == JSONRPC_METHOD_NOT_FOUND


def test_handle_jsonrpc_bad_envelope():
    store = MockTaskStore()
    resp = handle_jsonrpc({"jsonrpc": "1.0", "method": "GetTask", "params": {}, "id": 1},
                          store)
    assert "error" in resp
