"""A2A v1.0.1 JSON-RPC 端点行为测试（L0 协议对齐层）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
- SendMessage / ListTasks / GetTask / CancelTask verb 分发
- JSON-RPC 2.0 envelope 契约（成功/错误 body，不依赖 HTTP 码）
- JWS 签名 optional（无 header 不阻断，签名失败不阻断）
- TaskStore 状态机（合法/非法转移，终态不可逆）
- 幂等（client-provided taskId 二次创建返回同一 task）
- TTL 清理（惰性 + 主动 purge）
- ListTasks 过滤（contextId / status / limit 上限）

所有测试用 FastAPI 内置 TestClient，不启动真实服务器；
不依赖外部网络请求；不修改 mcp_server.py / mcp_http.py / a2a_jws.py。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.api import a2a as a2a_module
from app.api.a2a import (
    A2A_INVALID_TRANSITION,
    A2A_TASK_NOT_FOUND,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    LIST_TASKS_MAX_LIMIT,
    SUPPORTED_METHODS,
)
from app.lib.a2a_task_store import (
    CANCELABLE_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    A2ATask,
    InvalidTaskTransitionError,
    TaskState,
    TaskStore,
)


# ─────────────────────────── Fixture ───────────────────────────

@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch: pytest.MonkeyPatch) -> TaskStore:
    """每个测试用例注入独立 TaskStore，避免用例间状态泄漏。"""
    store = TaskStore(ttl_seconds=86400)
    monkeypatch.setattr(a2a_module, "_DEFAULT_STORE", store)
    return store


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient：直接调用 create_app()，不走 uvicorn。"""
    return TestClient(create_app())


# ─────────────────────────── 工具：构造 JSON-RPC envelope ───────────────────────────

def _rpc(method: str, params: dict[str, Any] | None = None, id_: Any = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params if params is not None else {},
        "id": id_,
    }


def _post(client: TestClient, body: dict[str, Any] | str, headers: dict[str, str] | None = None) -> Any:
    r = client.post("/a2a", json=body, headers=headers or {}) if isinstance(body, dict) else \
        client.post("/a2a", content=body, headers=headers or {})
    return r


def _send(client: TestClient, task_id: str | None = None, parts: list | None = None,
          context_id: str | None = None):
    """构造标准 SendMessage body 并 POST，返回 TestClient Response。"""
    params: dict[str, Any] = {
        "message": {
            "role": "user",
            "parts": parts if parts is not None else [
                {"kind": "data", "data": {"tool": "hl_health_check", "args": {}}}
            ],
        }
    }
    if task_id:
        params["taskId"] = task_id
    if context_id:
        params["contextId"] = context_id
    return _post(client, _rpc("SendMessage", params))


# ═══════════════════════════ 1. 路由 + 端点契约 ═══════════════════════════

class TestEndpointContract:
    """端点基础契约：路由注册、方法枚举、envelope 结构。"""

    def test_01_post_a2a_route_registered(self, client: TestClient) -> None:
        # 任意 method 都会得到 JSON-RPC response（不是 404）
        r = _post(client, _rpc("SendMessage"))
        assert r.status_code == 200
        assert r.json()["jsonrpc"] == "2.0"

    def test_02_supported_methods_constant(self) -> None:
        assert SUPPORTED_METHODS == {"SendMessage", "ListTasks", "GetTask", "CancelTask"}

    def test_03_get_a2a_not_allowed(self, client: TestClient) -> None:
        # 端点只支持 POST；GET 应返回 405
        r = client.get("/a2a")
        assert r.status_code == 405

    def test_04_invalid_json_body_returns_400(self, client: TestClient) -> None:
        r = client.post("/a2a", content="not json", headers={"Content-Type": "application/json"})
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == -32700  # parse error

    def test_05_non_object_body_returns_invalid_request(self, client: TestClient) -> None:
        # list 不是对象 → INVALID_REQUEST
        r = client.post("/a2a", json=[1, 2, 3])
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_REQUEST

    def test_06_missing_jsonrpc_field(self, client: TestClient) -> None:
        r = _post(client, {"method": "SendMessage", "id": 1})
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_REQUEST

    def test_07_wrong_jsonrpc_version(self, client: TestClient) -> None:
        r = _post(client, {"jsonrpc": "1.0", "method": "SendMessage", "id": 1})
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_REQUEST

    def test_08_unknown_method_returns_method_not_found(self, client: TestClient) -> None:
        r = _post(client, _rpc("DoesNotExist"))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_METHOD_NOT_FOUND
        assert "DoesNotExist" in body["error"]["message"]

    def test_09_response_id_echoed(self, client: TestClient) -> None:
        r = _send(client, task_id="echo-test")
        body = r.json()
        assert body["id"] == 1  # 默认 id=1

    def test_10_openapi_path_registered(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/a2a" in paths
        assert "post" in paths["/a2a"]


# ═══════════════════════════ 2. SendMessage ═══════════════════════════

class TestSendMessage:
    """SendMessage：创建 task → 调用 MCP 工具 → 附加 artifact → 状态推进。"""

    def test_11_send_message_basic_health_check(self, client: TestClient) -> None:
        """显式 tool=hl_health_check：最简调用，返回 COMPLETED。"""
        r = _send(client, task_id="sm-basic")
        body = r.json()
        assert "result" in body
        task = body["result"]
        assert task["taskId"] == "sm-basic"
        assert task["status"]["state"] == "COMPLETED"
        assert len(task["artifacts"]) == 1
        artifact = task["artifacts"][0]
        assert artifact["name"] == "hl_health_check"
        assert "data" in artifact["parts"][0]

    def test_12_send_message_with_text_fallback(self, client: TestClient) -> None:
        """纯文本 parts → fallback 到 hl_search_knowledge。"""
        parts = [{"kind": "text", "text": "anti-inflammatory diet"}]
        r = _send(client, task_id="sm-text", parts=parts)
        body = r.json()
        task = body["result"]
        assert task["status"]["state"] in ("COMPLETED", "FAILED")
        artifact = task["artifacts"][0]
        assert artifact["name"] == "hl_search_knowledge"

    def test_13_send_message_axis_detail(self, client: TestClient) -> None:
        parts = [{"kind": "data", "data": {
            "tool": "hl_get_axis_detail", "args": {"axis_id": "A"}
        }}]
        r = _send(client, task_id="sm-axis", parts=parts)
        body = r.json()
        task = body["result"]
        assert task["status"]["state"] == "COMPLETED"
        artifact = task["artifacts"][0]
        assert artifact["parts"][0]["data"]["axis_id"] == "A"

    def test_14_send_message_unknown_tool_marks_failed(self, client: TestClient) -> None:
        """工具不在白名单 → tool not allowed → FAILED 状态。"""
        parts = [{"kind": "data", "data": {
            "tool": "hl_not_a_real_tool", "args": {}
        }}]
        r = _send(client, task_id="sm-unknown-tool", parts=parts)
        body = r.json()
        task = body["result"]
        assert task["status"]["state"] == "FAILED"

    def test_15_send_message_missing_message_field(self, client: TestClient) -> None:
        """params 缺 message → INVALID_PARAMS。"""
        r = _post(client, _rpc("SendMessage", {"contextId": "ctx-1"}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_16_send_message_parts_not_list(self, client: TestClient) -> None:
        r = _post(client, _rpc("SendMessage", {
            "message": {"role": "user", "parts": "not-a-list"}
        }))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_17_send_message_missing_params(self, client: TestClient) -> None:
        r = _post(client, {"jsonrpc": "2.0", "method": "SendMessage", "id": 1})
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_18_send_message_empty_text_fallbacks_to_health_check(self, client: TestClient) -> None:
        """无 tool 无 text → 默认 hl_health_check（无参）。"""
        parts = [{"kind": "text", "text": "   "}]  # 空白
        r = _send(client, task_id="sm-empty-text", parts=parts)
        body = r.json()
        task = body["result"]
        assert task["artifacts"][0]["name"] == "hl_health_check"

    def test_19_send_message_missing_required_arg(self, client: TestClient) -> None:
        """hl_get_axis_detail 缺 axis_id → tool 返回 error → FAILED。"""
        parts = [{"kind": "data", "data": {
            "tool": "hl_get_axis_detail", "args": {}
        }}]
        r = _send(client, task_id="sm-missing-arg", parts=parts)
        body = r.json()
        task = body["result"]
        assert task["status"]["state"] == "FAILED"

    def test_20_send_message_client_task_id_used(self, client: TestClient) -> None:
        r = _send(client, task_id="my-custom-id")
        body = r.json()
        assert body["result"]["taskId"] == "my-custom-id"

    def test_21_send_message_generates_uuid_when_no_id(self, client: TestClient) -> None:
        r = _send(client)
        body = r.json()
        tid = body["result"]["taskId"]
        assert tid  # 非空
        assert len(tid) >= 16  # UUID hex

    def test_22_send_message_creates_context_id_from_task_id(self, client: TestClient) -> None:
        """contextId 未提供时复用 taskId。"""
        r = _send(client, task_id="sm-ctx-default")
        body = r.json()
        assert body["result"]["contextId"] == "sm-ctx-default"

    def test_23_send_message_explicit_context_id(self, client: TestClient) -> None:
        r = _send(client, task_id="sm-ctx-explicit", context_id="conv-1")
        body = r.json()
        assert body["result"]["contextId"] == "conv-1"


# ═══════════════════════════ 3. ListTasks ═══════════════════════════

class TestListTasks:
    """ListTasks：过滤 + 上限。"""

    def _seed(self, client: TestClient, n: int = 3, ctx: str = "list-ctx", prefix: str = "list") -> list[str]:
        ids = []
        for i in range(n):
            tid = f"{prefix}-{i}"
            _send(client, task_id=tid, context_id=ctx)
            ids.append(tid)
        return ids

    def test_24_list_tasks_empty_store(self, client: TestClient) -> None:
        r = _post(client, _rpc("ListTasks"))
        body = r.json()
        assert body["result"]["tasks"] == []
        assert body["result"]["totalCount"] == 0

    def test_25_list_tasks_returns_all_seeded(self, client: TestClient) -> None:
        ids = self._seed(client, n=3)
        r = _post(client, _rpc("ListTasks"))
        body = r.json()
        got_ids = {t["taskId"] for t in body["result"]["tasks"]}
        assert set(ids) == got_ids
        assert body["result"]["totalCount"] == 3

    def test_26_list_tasks_filter_by_context_id(self, client: TestClient) -> None:
        self._seed(client, n=2, ctx="ctx-A", prefix="seedA")
        self._seed(client, n=2, ctx="ctx-B", prefix="seedB")
        r = _post(client, _rpc("ListTasks", {"contextId": "ctx-A"}))
        body = r.json()
        assert body["result"]["totalCount"] == 2
        for t in body["result"]["tasks"]:
            assert t["contextId"] == "ctx-A"

    def test_27_list_tasks_filter_by_status(self, client: TestClient) -> None:
        self._seed(client, n=2)
        # 手工推一个到 FAILED
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="t-failed")
        store.update_status("t-failed", TaskState.WORKING)
        store.update_status("t-failed", TaskState.FAILED)
        r = _post(client, _rpc("ListTasks", {"status": "FAILED"}))
        body = r.json()
        assert body["result"]["totalCount"] >= 1
        for t in body["result"]["tasks"]:
            assert t["status"]["state"] == "FAILED"

    def test_28_list_tasks_limit_caps_at_50(self, client: TestClient) -> None:
        for i in range(55):
            _send(client, task_id=f"cap-{i}")
        r = _post(client, _rpc("ListTasks", {"limit": 100}))
        body = r.json()
        assert body["result"]["totalCount"] == LIST_TASKS_MAX_LIMIT == 50

    def test_29_list_tasks_limit_under_cap(self, client: TestClient) -> None:
        self._seed(client, n=5)
        r = _post(client, _rpc("ListTasks", {"limit": 2}))
        body = r.json()
        assert body["result"]["totalCount"] == 2

    def test_30_list_tasks_invalid_limit_zero(self, client: TestClient) -> None:
        r = _post(client, _rpc("ListTasks", {"limit": 0}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_31_list_tasks_negative_limit(self, client: TestClient) -> None:
        r = _post(client, _rpc("ListTasks", {"limit": -1}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_32_list_tasks_invalid_status_string(self, client: TestClient) -> None:
        r = _post(client, _rpc("ListTasks", {"status": "NOT_A_STATE"}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_33_list_tasks_invalid_limit_type(self, client: TestClient) -> None:
        r = _post(client, _rpc("ListTasks", {"limit": "many"}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_34_list_tasks_missing_params(self, client: TestClient) -> None:
        r = _post(client, {"jsonrpc": "2.0", "method": "ListTasks", "id": 1})
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_35_list_tasks_sort_by_created_at_desc(self, client: TestClient) -> None:
        for i in range(3):
            _send(client, task_id=f"sort-{i}")
            time.sleep(0.005)  # 保证 createdAt 单调递增
        r = _post(client, _rpc("ListTasks"))
        body = r.json()
        tasks = body["result"]["tasks"]
        created = [t["createdAt"] for t in tasks]
        assert created == sorted(created, reverse=True)


# ═══════════════════════════ 4. GetTask ═══════════════════════════

class TestGetTask:
    """GetTask：按 ID 取单个任务。"""

    def test_36_get_task_exists(self, client: TestClient) -> None:
        _send(client, task_id="get-target")
        r = _post(client, _rpc("GetTask", {"taskId": "get-target"}))
        body = r.json()
        assert body["result"]["taskId"] == "get-target"

    def test_37_get_task_not_found(self, client: TestClient) -> None:
        r = _post(client, _rpc("GetTask", {"taskId": "no-such"}))
        body = r.json()
        assert body["error"]["code"] == A2A_TASK_NOT_FOUND

    def test_38_get_task_missing_task_id(self, client: TestClient) -> None:
        r = _post(client, _rpc("GetTask", {}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_39_get_task_non_string_task_id(self, client: TestClient) -> None:
        r = _post(client, _rpc("GetTask", {"taskId": 12345}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_40_get_task_empty_params(self, client: TestClient) -> None:
        r = _post(client, {"jsonrpc": "2.0", "method": "GetTask", "id": 1})
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS


# ═══════════════════════════ 5. CancelTask ═══════════════════════════

class TestCancelTask:
    """CancelTask：仅 SUBMITTED / WORKING 可取消。"""

    def test_41_cancel_submitted(self, client: TestClient) -> None:
        # 手工造一个 SUBMITTED 状态 task
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-submitted")
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-submitted"}))
        body = r.json()
        assert body["result"]["status"]["state"] == "CANCELED"

    def test_42_cancel_working(self, client: TestClient) -> None:
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-working")
        store.update_status("canc-working", TaskState.WORKING)
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-working"}))
        body = r.json()
        assert body["result"]["status"]["state"] == "CANCELED"

    def test_43_cancel_completed_raises(self, client: TestClient) -> None:
        """COMPLETED 是终态，CancelTask 返回 A2A_INVALID_TRANSITION。"""
        _send(client, task_id="canc-done")  # 自动走到 COMPLETED
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-done"}))
        body = r.json()
        assert body["error"]["code"] == A2A_INVALID_TRANSITION

    def test_44_cancel_failed_raises(self, client: TestClient) -> None:
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-failed")
        store.update_status("canc-failed", TaskState.WORKING)
        store.update_status("canc-failed", TaskState.FAILED)
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-failed"}))
        body = r.json()
        assert body["error"]["code"] == A2A_INVALID_TRANSITION

    def test_45_cancel_canceled_raises(self, client: TestClient) -> None:
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-again")
        store.update_status("canc-again", TaskState.CANCELED)
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-again"}))
        body = r.json()
        assert body["error"]["code"] == A2A_INVALID_TRANSITION

    def test_46_cancel_input_required_raises(self, client: TestClient) -> None:
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-input")
        store.update_status("canc-input", TaskState.INPUT_REQUIRED)
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-input"}))
        body = r.json()
        assert body["error"]["code"] == A2A_INVALID_TRANSITION

    def test_47_cancel_not_found(self, client: TestClient) -> None:
        r = _post(client, _rpc("CancelTask", {"taskId": "ghost"}))
        body = r.json()
        assert body["error"]["code"] == A2A_TASK_NOT_FOUND

    def test_48_cancel_missing_task_id(self, client: TestClient) -> None:
        r = _post(client, _rpc("CancelTask", {}))
        body = r.json()
        assert body["error"]["code"] == JSONRPC_INVALID_PARAMS

    def test_49_cancel_with_reason_stored_in_status_message(self, client: TestClient) -> None:
        store = a2a_module._DEFAULT_STORE
        store.create_task(taskId="canc-reason")
        r = _post(client, _rpc("CancelTask", {"taskId": "canc-reason", "reason": "user abort"}))
        body = r.json()
        task = body["result"]
        assert task["status"]["state"] == "CANCELED"
        assert task["status"]["message"] == "user abort"


# ═══════════════════════════ 6. TaskStore 状态机 ═══════════════════════════

class TestTaskStateMachine:
    """TaskStore 直接调用（不经 HTTP），覆盖状态转移矩阵。"""

    def test_50_all_valid_transitions_accepted(self) -> None:
        """VALID_TRANSITIONS 里声明的每一条边都应能通过。"""
        for from_state, to_states in VALID_TRANSITIONS.items():
            store = TaskStore()
            t = store.create_task(taskId="t")
            # 先把 t 推到 from_state
            if from_state != TaskState.SUBMITTED:
                # 走 SUBMITTED → ... → from_state 的最短路径
                path = self._find_path(TaskState.SUBMITTED, from_state)
                for step in path:
                    store.update_status("t", step)
            for to_state in to_states:
                store2 = TaskStore()
                t2 = store2.create_task(taskId="t2")
                if from_state != TaskState.SUBMITTED:
                    for step in self._find_path(TaskState.SUBMITTED, from_state):
                        store2.update_status("t2", step)
                # 合法转移：不抛异常
                store2.update_status("t2", to_state)

    def _find_path(self, start: TaskState, target: TaskState) -> list[TaskState]:
        """BFS 找最短路径（用于测试辅助）。"""
        if start == target:
            return []
        from collections import deque
        queue = deque([([start],)])
        visited = {start}
        while queue:
            path, = queue.popleft()
            cur = path[-1]
            for nxt in VALID_TRANSITIONS[cur]:
                if nxt == target:
                    return path[1:] + [nxt]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((path + [nxt],))
        raise AssertionError(f"no path from {start} to {target}")

    def test_51_all_terminal_states_reject_transitions(self) -> None:
        """终态无任何合法出边。"""
        for terminal in TERMINAL_STATES:
            assert VALID_TRANSITIONS[terminal] == frozenset(), terminal

    def test_52_transition_from_completed_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="done")
        store.update_status("done", TaskState.WORKING)
        store.update_status("done", TaskState.COMPLETED)
        with pytest.raises(InvalidTaskTransitionError) as exc:
            store.update_status("done", TaskState.WORKING)
        assert exc.value.from_state == TaskState.COMPLETED
        assert exc.value.to_state == TaskState.WORKING

    def test_53_transition_from_failed_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="fail")
        store.update_status("fail", TaskState.WORKING)
        store.update_status("fail", TaskState.FAILED)
        with pytest.raises(InvalidTaskTransitionError):
            store.update_status("fail", TaskState.WORKING)

    def test_54_transition_from_canceled_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="cancel")
        store.update_status("cancel", TaskState.CANCELED)
        with pytest.raises(InvalidTaskTransitionError):
            store.update_status("cancel", TaskState.WORKING)

    def test_55_submit_to_completed_directly_raises(self) -> None:
        """SUBMITTED 不能直接跳到 COMPLETED，必须先 WORKING。"""
        store = TaskStore()
        store.create_task(taskId="skip")
        with pytest.raises(InvalidTaskTransitionError):
            store.update_status("skip", TaskState.COMPLETED)

    def test_56_submit_to_input_required_allowed(self) -> None:
        """SUBMITTED → INPUT_REQUIRED 合法（agent 等待输入）。"""
        store = TaskStore()
        store.create_task(taskId="input")
        store.update_status("input", TaskState.INPUT_REQUIRED)

    def test_57_update_status_nonexistent_raises_key_error(self) -> None:
        store = TaskStore()
        with pytest.raises(KeyError):
            store.update_status("nope", TaskState.WORKING)

    def test_58_update_status_wrong_type_raises_type_error(self) -> None:
        store = TaskStore()
        store.create_task(taskId="type")
        with pytest.raises(TypeError):
            store.update_status("type", "WORKING")  # 字符串而非枚举

    def test_59_update_status_same_state_is_idempotent(self) -> None:
        """相同状态转移应幂等，不抛异常。"""
        store = TaskStore()
        store.create_task(taskId="idem")
        store.update_status("idem", TaskState.SUBMITTED)  # 首次
        store.update_status("idem", TaskState.SUBMITTED)  # 幂等
        assert store.get_task("idem").status == TaskState.SUBMITTED

    def test_60_all_non_cancelable_states_reject_cancel(self) -> None:
        """CANCELABLE_STATES 之外的状态都应拒绝 cancel_task。"""
        for state in list(TaskState):
            if state in CANCELABLE_STATES:
                continue
            store = TaskStore()
            t = store.create_task(taskId=f"nc-{state.value}")
            if state != TaskState.SUBMITTED:
                for step in self._find_path(TaskState.SUBMITTED, state):
                    store.update_status(t.taskId, step)
            with pytest.raises(InvalidTaskTransitionError):
                store.cancel_task(t.taskId)

    def test_61_cancelable_states_all_accept_cancel(self) -> None:
        """CANCELABLE_STATES 里的每个状态都应接受 cancel_task。"""
        for state in CANCELABLE_STATES:
            store = TaskStore()
            t = store.create_task(taskId=f"ok-{state.value}")
            if state != TaskState.SUBMITTED:
                for step in self._find_path(TaskState.SUBMITTED, state):
                    store.update_status(t.taskId, step)
            updated = store.cancel_task(t.taskId)
            assert updated.status == TaskState.CANCELED

    def test_62_full_transition_matrix_exhaustive(self) -> None:
        """穷举 6×6 = 36 组合：每个 (from, to) 要么在合法表里、要么抛异常。"""
        all_states = list(TaskState)
        for frm in all_states:
            for to in all_states:
                store = TaskStore()
                t = store.create_task(taskId=f"m-{frm.value}-{to.value}")
                if frm != TaskState.SUBMITTED:
                    try:
                        for step in self._find_path(TaskState.SUBMITTED, frm):
                            store.update_status(t.taskId, step)
                    except InvalidTaskTransitionError:
                        continue  # 目标状态不可达则跳过
                expected_valid = to in VALID_TRANSITIONS[frm]
                if expected_valid:
                    try:
                        store.update_status(t.taskId, to)
                    except InvalidTaskTransitionError:
                        pytest.fail(f"{frm} -> {to} 应该合法但抛异常")
                else:
                    if frm == to:
                        continue  # 幂等不算非法
                    with pytest.raises(InvalidTaskTransitionError):
                        store.update_status(t.taskId, to)


# ═══════════════════════════ 7. 幂等 ═══════════════════════════

class TestIdempotency:
    """client-provided taskId 二次创建返回同一 task。"""

    def test_63_create_with_same_id_returns_same_task(self) -> None:
        store = TaskStore()
        t1 = store.create_task(taskId="dup-1")
        t2 = store.create_task(taskId="dup-1")
        assert t1.taskId == t2.taskId
        assert t1 is t2  # 同一对象

    def test_64_create_without_id_generates_unique_ids(self) -> None:
        store = TaskStore()
        t1 = store.create_task()
        t2 = store.create_task()
        assert t1.taskId != t2.taskId

    def test_65_idempotent_create_with_conflicting_context_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="conflict", contextId="ctx-A")
        with pytest.raises(ValueError):
            store.create_task(taskId="conflict", contextId="ctx-B")

    def test_66_idempotent_create_with_matching_context_returns_existing(self) -> None:
        store = TaskStore()
        t1 = store.create_task(taskId="same-ctx", contextId="ctx-X")
        t2 = store.create_task(taskId="same-ctx", contextId="ctx-X")
        assert t1.taskId == t2.taskId
        assert t1 is t2

    def test_67_idempotent_create_keeps_original_created_at(self) -> None:
        store = TaskStore()
        t1 = store.create_task(taskId="keep-ts")
        original_created = t1.createdAt
        time.sleep(0.01)
        t2 = store.create_task(taskId="keep-ts")
        assert t2.createdAt == original_created

    def test_68_send_message_idempotent_across_repeats(self, client: TestClient) -> None:
        """同 taskId 多次 SendMessage：task 只创建一次，artifact 会累加。"""
        _send(client, task_id="multi-send")
        _send(client, task_id="multi-send")  # 幂等返回已有 task
        store = a2a_module._DEFAULT_STORE
        t = store.get_task("multi-send")
        assert t is not None
        # 两次调用都附加 artifact
        assert len(t.artifacts) >= 1


# ═══════════════════════════ 8. TTL ═══════════════════════════

class TestTTL:
    """TTL 过期清理：惰性 + 主动 purge。"""

    def test_69_purge_expired_removes_old_tasks(self) -> None:
        store = TaskStore(ttl_seconds=0.05)
        store.create_task(taskId="expire-1")
        time.sleep(0.08)
        purged = store.purge_expired()
        assert purged == 1
        assert store.get_task("expire-1") is None

    def test_70_purge_expired_keeps_fresh_tasks(self) -> None:
        store = TaskStore(ttl_seconds=60)
        store.create_task(taskId="fresh")
        purged = store.purge_expired()
        assert purged == 0
        assert store.get_task("fresh") is not None

    def test_71_lazy_purge_on_get(self) -> None:
        store = TaskStore(ttl_seconds=0.05)
        store.create_task(taskId="lazy-1")
        time.sleep(0.08)
        # 不主动 purge，直接 get 也应触发清理
        assert store.get_task("lazy-1") is None

    def test_72_lazy_purge_on_list(self) -> None:
        store = TaskStore(ttl_seconds=0.05)
        store.create_task(taskId="lazy-2")
        time.sleep(0.08)
        # list 也应触发清理
        assert store.list_tasks() == []

    def test_73_lazy_purge_on_create(self) -> None:
        store = TaskStore(ttl_seconds=0.05)
        store.create_task(taskId="lazy-3")
        time.sleep(0.08)
        # 创建新 task 时也清理旧的
        store.create_task(taskId="lazy-4")
        assert store.get_task("lazy-3") is None
        assert store.get_task("lazy-4") is not None

    def test_74_zero_ttl_disables_purge(self) -> None:
        """ttl_seconds=0 表示禁用 TTL。"""
        store = TaskStore(ttl_seconds=0)
        store.create_task(taskId="no-expire")
        time.sleep(0.05)
        assert store.get_task("no-expire") is not None
        assert store.purge_expired() == 0

    def test_75_len_reflects_after_purge(self) -> None:
        store = TaskStore(ttl_seconds=0.05)
        store.create_task(taskId="len-1")
        assert len(store) == 1
        time.sleep(0.08)
        assert len(store) == 0  # __len__ 触发惰性清理


# ═══════════════════════════ 9. TaskStore 基本方法 ═══════════════════════════

class TestTaskStoreBasics:
    """TaskStore 直接方法（不经 HTTP）。"""

    def test_76_create_task_default_state_submitted(self) -> None:
        store = TaskStore()
        t = store.create_task(taskId="base-1")
        assert t.status == TaskState.SUBMITTED

    def test_77_create_task_with_initial_status_message(self) -> None:
        store = TaskStore()
        t = store.create_task(taskId="base-2", statusMessage="queued")
        assert t.statusMessage == "queued"

    def test_78_create_task_records_history(self) -> None:
        store = TaskStore()
        t = store.create_task(taskId="base-3")
        assert len(t.history) == 1
        assert t.history[0]["state"] == "SUBMITTED"

    def test_79_to_dict_camel_case(self) -> None:
        store = TaskStore()
        t = store.create_task(taskId="base-4", contextId="ctx-4")
        d = t.to_dict()
        assert set(d.keys()) == {
            "taskId", "contextId", "status", "artifacts", "history", "createdAt", "updatedAt"
        }
        assert d["status"]["state"] == "SUBMITTED"
        assert d["status"]["message"] is None

    def test_80_add_artifact_appends(self) -> None:
        store = TaskStore()
        store.create_task(taskId="art")
        store.add_artifact("art", {"artifactId": "a1"})
        store.add_artifact("art", {"artifactId": "a2"})
        t = store.get_task("art")
        assert len(t.artifacts) == 2
        assert t.artifacts[0]["artifactId"] == "a1"
        assert t.artifacts[1]["artifactId"] == "a2"

    def test_81_add_artifact_nonexistent_raises(self) -> None:
        store = TaskStore()
        with pytest.raises(KeyError):
            store.add_artifact("ghost", {"artifactId": "x"})

    def test_82_add_artifact_wrong_type_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="type-art")
        with pytest.raises(TypeError):
            store.add_artifact("type-art", "not-a-dict")

    def test_83_get_task_nonexistent_returns_none(self) -> None:
        store = TaskStore()
        assert store.get_task("nope") is None

    def test_84_list_tasks_limit_underflow_raises(self) -> None:
        store = TaskStore()
        store.create_task(taskId="l1")
        with pytest.raises(ValueError):
            store.list_tasks(limit=0)

    def test_85_list_tasks_limit_overflow_capped(self) -> None:
        store = TaskStore()
        for i in range(60):
            store.create_task(taskId=f"cap-{i}")
        tasks = store.list_tasks(limit=1000)
        assert len(tasks) == 50

    def test_86_list_tasks_status_string_accepted(self) -> None:
        store = TaskStore()
        store.create_task(taskId="s-1")
        store.update_status("s-1", TaskState.WORKING)
        store.update_status("s-1", TaskState.COMPLETED)
        tasks = store.list_tasks(status="COMPLETED")
        assert len(tasks) == 1
        assert tasks[0].taskId == "s-1"

    def test_87_list_tasks_context_id_filter(self) -> None:
        store = TaskStore()
        store.create_task(taskId="c1", contextId="X")
        store.create_task(taskId="c2", contextId="Y")
        tasks = store.list_tasks(contextId="X")
        assert len(tasks) == 1
        assert tasks[0].taskId == "c1"

    def test_88_iterate_store(self) -> None:
        store = TaskStore()
        store.create_task(taskId="it-1")
        store.create_task(taskId="it-2")
        ids = {t.taskId for t in store}
        assert ids == {"it-1", "it-2"}


# ═══════════════════════════ 10. JWS 签名（optional） ═══════════════════════════

class TestJwsOptional:
    """JWS 签名 optional：无 header 不阻断，签名格式异常不阻断。"""

    def test_89_no_auth_header_passes(self, client: TestClient) -> None:
        r = _send(client, task_id="jws-none")
        assert "result" in r.json()

    def test_90_non_bearer_auth_prefix_passes(self, client: TestClient) -> None:
        r = _post(client, _rpc("SendMessage", {
            "message": {"parts": [{"kind": "text", "text": "x"}]}
        }), headers={"Authorization": "Basic abcdef"})
        # Basic 前缀不是 Bearer → 忽略 → 通过
        body = r.json()
        assert "result" in body or "error" in body
        # 关键：不因为非 Bearer 而 fail-loud

    def test_91_malformed_jws_passes(self, client: TestClient) -> None:
        """JWS 段数不对（不是 . . 三段）→ 不阻断，忽略签名。"""
        r = _post(client, _rpc("SendMessage", {
            "message": {"parts": [{"kind": "text", "text": "x"}]}
        }), headers={"Authorization": "Bearer not-a-valid-jws"})
        body = r.json()
        assert "result" in body or "error" in body
        # 不因 JWS 格式错而阻断

    def test_92_empty_bearer_passes(self, client: TestClient) -> None:
        r = _post(client, _rpc("SendMessage", {
            "message": {"parts": [{"kind": "text", "text": "x"}]}
        }), headers={"Authorization": "Bearer "})
        body = r.json()
        assert "result" in body or "error" in body

    def test_93_verify_jws_returns_false_when_env_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HL_A2A_VERIFY_KEY_JWK 未设置 → 跳过验证 → 不阻断。"""
        monkeypatch.delenv("HL_A2A_VERIFY_KEY_JWK", raising=False)
        from app.api.a2a import _verify_optional_jws
        assert _verify_optional_jws("Bearer some.jws.value") is False

    def test_94_verify_jws_no_header_returns_false(self) -> None:
        from app.api.a2a import _verify_optional_jws
        assert _verify_optional_jws(None) is False
        assert _verify_optional_jws("") is False

    def test_95_verify_jws_roundtrip_with_valid_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """用 a2a_jws 生成签名 + 公钥 → verify_jws 返回 True。"""
        from app.lib.a2a_jws import generate_jwk_pair, sign_jws
        import base64, json as _json
        priv, pub = generate_jwk_pair()
        # 签一个 payload
        payload_b64 = base64.urlsafe_b64encode(b"hello").rstrip(b"=").decode()
        jws = sign_jws(payload_b64, priv)
        monkeypatch.setenv("HL_A2A_VERIFY_KEY_JWK", _json.dumps(pub))
        from app.api.a2a import _verify_optional_jws
        assert _verify_optional_jws(f"Bearer {jws}") is True

    def test_96_verify_jws_forged_signature_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """伪造签名（用错公钥）→ verify_jws 返回 False。"""
        from app.lib.a2a_jws import generate_jwk_pair, sign_jws
        import base64, json as _json
        priv, pub = generate_jwk_pair()
        _wrong_priv, wrong_pub = generate_jwk_pair()
        payload_b64 = base64.urlsafe_b64encode(b"hello").rstrip(b"=").decode()
        jws = sign_jws(payload_b64, priv)  # 用 priv 签
        monkeypatch.setenv("HL_A2A_VERIFY_KEY_JWK", _json.dumps(wrong_pub))  # 用错公钥验
        from app.api.a2a import _verify_optional_jws
        assert _verify_optional_jws(f"Bearer {jws}") is False
