"""A2A v1.0.1 JSON-RPC 端点（L0 协议对齐层）。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「L0 协议对齐：A2A v1.0.1 SendMessage / ListTasks / GetTask / CancelTask」。

A2A v1.0.1 spec：https://google.github.io/A2A/specification/v1.0.1/

定位：
- **单一端点**：`POST /a2a`，JSON-RPC 2.0 envelope（method 字段做 verb 分发），
  与 spec 的"single JSON-RPC endpoint"约束严格对齐。
- **薄包装 SendMessage**：不重写业务逻辑，只做"把 A2A Message → 调用现有
  MCP 工具函数 → 把结果作为 artifact 附加到 task"的编排。可用工具见
  `healthlens_agent.mcp_server` 的 L1/L2 层：
      hl_health_check / hl_search_knowledge / hl_get_axis_detail /
      hl_get_wellness_article / hl_suggest_general_diet /
      hl_suggest_general_motion
  L3 工具默认不接入（需 HL_MCP_EXPOSE_PRIVATE=1）。
- **JWS 签名 optional**：若 `Authorization: Bearer <jws>` 出现则用
  `app.lib.a2a_jws.verify_jws` 验证；无 header 或验证失败均**不阻断请求**
  （对齐 A2A "optional signature" 语义），只在响应里带 `signed: false/true`。
- **fail-loud 状态转移**：非法状态转移返回 JSON-RPC 错误码 -32001，
  HTTP 状态码仍为 200（JSON-RPC 语义要求错误走 body 而非 HTTP 码）。

Wellness 平台术语纪律：本端点仅暴露 wellness 知识工具，不做健康诊断。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.lib.a2a_jws import verify_jws
from app.lib.a2a_task_store import (
    A2ATask,
    InvalidTaskTransitionError,
    TaskState,
    TaskStore,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["A2A v1.0.1"])

# ─────────────────────────── JSON-RPC 错误码 ───────────────────────────

# 标准 JSON-RPC 2.0 保留码（-32700 到 -32600） + A2A 建议的应用码（-32000 系列）
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

# A2A 语义错误
A2A_TASK_NOT_FOUND = -32001
A2A_INVALID_TRANSITION = -32002
A2A_AUTHENTICATION_REQUIRED = -32003

# 已知 verb
SUPPORTED_METHODS: frozenset[str] = frozenset(
    {"SendMessage", "ListTasks", "GetTask", "CancelTask"}
)

# ListTasks 硬上限（A2A v1.0.1 spec）
LIST_TASKS_MAX_LIMIT = 50

# 进程内单例任务存储（生产部署应替换为 DB/Redis 后端）
_DEFAULT_STORE = TaskStore()


# ─────────────────────────── 工具白名单（复用 MCP 工具函数） ───────────────────────────

# SendMessage 允许客户端显式指定要调用的 MCP 工具。key = tool name，
# value = (必需参数, 参数类型提示，仅文档用)。
# 严格对齐 healthlens_agent/mcp_server.py 的 L1 + L2 工具集，L3 不接入。
_ALLOWED_TOOL_DISPATCH: dict[str, tuple[str, ...]] = {
    # L1
    "hl_health_check": (),
    "hl_search_knowledge": ("query",),
    "hl_get_axis_detail": ("axis_id",),
    "hl_get_wellness_article": ("slug",),
    # L2
    "hl_suggest_general_diet": ("goal",),
    "hl_suggest_general_motion": ("intensity",),
}

# 若客户端未指定 tool，则用 message.parts[0].text 做最简启发式路由：
# 提取第一个可读文本作为 `hl_search_knowledge(query=...)`。
_DEFAULT_TOOL = "hl_search_knowledge"


def _load_tool_handler(tool_name: str):
    """从 mcp_server 加载 L1/L2 工具的 handler。

    Raises:
        KeyError: 工具不存在（非 L1/L2 或名字拼错）
    """
    # 惰性 import：避免循环依赖 + 让 mcp_server 的 sys.path 补丁生效
    from healthlens_agent.mcp_server import _active_tools  # type: ignore[import-not-found]

    tools = _active_tools()
    if tool_name not in tools:
        raise KeyError(tool_name)
    return tools[tool_name]["handler"]


def _resolve_message_to_tool_call(message: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """从 A2A Message 解析出 (tool_name, args)。

    支持两种调用形式：
    1. message.parts[0].data 里显式带 tool / args：
       {"kind":"data","data":{"tool":"hl_get_axis_detail","args":{"axis_id":"A"}}}
       —— 客户端最可控的形式，优先走此分支。
    2. 纯文本 parts：把第一个文本部分作为 hl_search_knowledge 的 query。
    """
    parts = message.get("parts") or []
    for part in parts:
        if not isinstance(part, dict):
            continue
        data = part.get("data")
        if isinstance(data, dict) and isinstance(data.get("tool"), str):
            tool_name = data["tool"]
            args = data.get("args") if isinstance(data.get("args"), dict) else {}
            if tool_name not in _ALLOWED_TOOL_DISPATCH:
                raise KeyError(tool_name)
            return tool_name, args

    # fallback：从 text part 抽 query
    text_bits: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_bits.append(part["text"])
    query = " ".join(text_bits).strip()
    if not query:
        # 无文本也无 data → 默认走 health_check（无参，最安全）
        return "hl_health_check", {}
    return _DEFAULT_TOOL, {"query": query}


def _execute_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """同步调用工具函数，统一异常包装为 artifact dict。"""
    required = _ALLOWED_TOOL_DISPATCH[tool_name]
    missing = [k for k in required if k not in args]
    if missing:
        return {
            "error": "missing_required_args",
            "tool": tool_name,
            "missing": missing,
        }
    handler = _load_tool_handler(tool_name)
    try:
        result = handler(**args)
    except Exception as exc:  # noqa: BLE001 - 边界层必须兜底
        logger.exception("a2a SendMessage tool call failed: %s", tool_name)
        return {"error": "tool_execution_failed", "tool": tool_name, "message": str(exc)}
    if not isinstance(result, dict):
        result = {"value": result}
    return {**result, "_tool": tool_name}


# ─────────────────────────── JSON-RPC 响应辅助 ───────────────────────────

def _ok(req_id: Any, result: Any, *, signed: bool = False) -> JSONResponse:
    body = {"jsonrpc": "2.0", "result": result, "id": req_id}
    if signed:
        body["signed"] = True
    return JSONResponse(content=body)


def _err(req_id: Any, code: int, message: str, data: Any = None) -> JSONResponse:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return JSONResponse(
        content={"jsonrpc": "2.0", "error": err, "id": req_id}
    )


# ─────────────────────────── JWS 校验（optional） ───────────────────────────

def _verify_optional_jws(auth_header: str | None) -> bool:
    """验证 Bearer JWS（optional，失败不阻断）。

    Returns:
        True:  请求带 JWS 且验证通过
        False: 无 header / 验证失败 / 解析失败（均不阻断，仅记录）
    """
    if not auth_header:
        return False
    if not auth_header.lower().startswith("bearer "):
        return False
    jws = auth_header[len("bearer "):].strip()
    if not jws or jws.count(".") != 2:
        return False

    # 使用 a2a_jws.verify_jws（JWS compact 格式）；需要 public JWK。
    # 生产部署应从 HL_A2A_VERIFY_KEY_JWK 环境变量读公钥。
    pub_jwk_raw = os.environ.get("HL_A2A_VERIFY_KEY_JWK", "")
    if not pub_jwk_raw:
        logger.debug("HL_A2A_VERIFY_KEY_JWK not set; skipping JWS verification")
        return False
    try:
        pub_jwk = json.loads(pub_jwk_raw)
    except json.JSONDecodeError:
        return False
    try:
        return bool(verify_jws(jws, pub_jwk))
    except Exception as exc:  # noqa: BLE001
        logger.warning("JWS verification raised: %s", exc)
        return False


# ─────────────────────────── Method handlers ───────────────────────────

def _handle_send_message(
    params: dict[str, Any],
    store: TaskStore,
) -> tuple[dict[str, Any], int]:
    """SendMessage: 创建 task → 同步执行工具 → 附加 artifact → 返回 COMPLETED。

    返回 (result_dict, jsonrpc_error_code)。result_dict 为 None 时表示要返
    回错误 envelope（用第二个返回值的错误码）。
    """
    if not isinstance(params, dict):
        return {}, JSONRPC_INVALID_PARAMS
    message = params.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("parts"), list):
        return {}, JSONRPC_INVALID_PARAMS

    # contextId / taskId 由客户端或消息头决定，缺失则自动生成
    context_id = params.get("contextId") or message.get("contextId")
    client_task_id = params.get("taskId")
    status_msg = params.get("statusMessage")

    # 1. 创建 task（幂等）
    task = store.create_task(
        taskId=client_task_id,
        contextId=context_id,
        statusMessage=status_msg,
    )

    # 2. SUBMITTED → WORKING
    try:
        store.update_status(task.taskId, TaskState.WORKING)
    except InvalidTaskTransitionError:
        # 幂等：task 已 WORKING/终态时跳过，不再推进
        pass

    # 3. 解析工具调用
    try:
        tool_name, args = _resolve_message_to_tool_call(message)
    except KeyError as exc:
        # 工具名不在白名单 → 标 FAILED，返回 task（让客户端看到失败原因）
        try:
            store.update_status(
                task.taskId,
                TaskState.FAILED,
                statusMessage=f"tool not allowed: {exc.args[0] if exc.args else 'unknown'}",
            )
        except InvalidTaskTransitionError:
            pass
        return store.get_task(task.taskId).to_dict(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("SendMessage message resolution failed")
        try:
            store.update_status(task.taskId, TaskState.FAILED, statusMessage=str(exc))
        except InvalidTaskTransitionError:
            pass
        return store.get_task(task.taskId).to_dict(), None

    tool_result = _execute_tool(tool_name, args)

    # 4. 附加 artifact
    artifact = {
        "artifactId": f"artifact-{task.taskId}",
        "parts": [{"kind": "data", "data": tool_result}],
        "name": tool_name,
    }
    store.add_artifact(task.taskId, artifact)

    # 5. WORKING → COMPLETED
    has_error = isinstance(tool_result, dict) and "error" in tool_result
    if has_error:
        # 工具返回结构化 error（如工具名拼错 / 参数缺失），标为 FAILED
        try:
            store.update_status(
                task.taskId,
                TaskState.FAILED,
                statusMessage=json.dumps(tool_result, ensure_ascii=False)[:500],
            )
        except InvalidTaskTransitionError:
            pass
    else:
        try:
            store.update_status(
                task.taskId, TaskState.COMPLETED, statusMessage="ok"
            )
        except InvalidTaskTransitionError:
            pass

    result = store.get_task(task.taskId).to_dict()
    return result, None


def _handle_list_tasks(params: dict[str, Any], store: TaskStore) -> tuple[dict[str, Any], int]:
    if not isinstance(params, dict):
        return {}, JSONRPC_INVALID_PARAMS
    context_id = params.get("contextId")
    status_raw = params.get("status")
    limit = params.get("limit", LIST_TASKS_MAX_LIMIT)
    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        return {}, JSONRPC_INVALID_PARAMS
    try:
        tasks = store.list_tasks(
            contextId=context_id,
            status=status_raw,
            limit=limit_int,
        )
    except ValueError:
        # status 非法 / limit 越界 → INVALID_PARAMS
        return {}, JSONRPC_INVALID_PARAMS
    return {
        "tasks": [t.to_dict() for t in tasks],
        "totalCount": len(tasks),
    }, None


def _handle_get_task(params: dict[str, Any], store: TaskStore) -> tuple[dict[str, Any], int]:
    if not isinstance(params, dict):
        return {}, JSONRPC_INVALID_PARAMS
    task_id = params.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        return {}, JSONRPC_INVALID_PARAMS
    task = store.get_task(task_id)
    if task is None:
        return {}, A2A_TASK_NOT_FOUND
    return task.to_dict(), None


def _handle_cancel_task(params: dict[str, Any], store: TaskStore) -> tuple[dict[str, Any], int]:
    if not isinstance(params, dict):
        return {}, JSONRPC_INVALID_PARAMS
    task_id = params.get("taskId")
    if not isinstance(task_id, str) or not task_id:
        return {}, JSONRPC_INVALID_PARAMS
    reason = params.get("reason")
    try:
        task = store.cancel_task(task_id, statusMessage=reason)
    except KeyError:
        return {}, A2A_TASK_NOT_FOUND
    except InvalidTaskTransitionError as exc:
        return {}, A2A_INVALID_TRANSITION
    return task.to_dict(), None


# ─────────────────────────── 单端点 ───────────────────────────

@router.post(
    "/a2a",
    summary="A2A v1.0.1 JSON-RPC 2.0 endpoint（SendMessage / ListTasks / GetTask / CancelTask）",
    tags=["A2A v1.0.1"],
    responses={
        200: {"description": "JSON-RPC response (success or error envelope)"},
        400: {"description": "Malformed JSON body"},
    },
)
async def a2a_jsonrpc_endpoint(request: Request) -> JSONResponse:
    """A2A v1.0.1 单一 JSON-RPC 端点。

    请求体：`{"jsonrpc":"2.0","method":"<verb>","params":{...},"id":...}`
    响应体：`{"jsonrpc":"2.0","result":{...},"id":...}` 或
            `{"jsonrpc":"2.0","error":{"code":...,"message":...},"id":...}`

    HTTP 状态码约定：
    - 200：JSON-RPC 层成功或协议内错误（含 method_not_found / invalid_params 等）
    - 400：body 不是合法 JSON 或不是对象

    JWS 签名 optional：如 `Authorization: Bearer <jws>` 存在且验证通过，
    响应体带 `"signed": true`；无 header 或验证失败则不带该字段（不阻断）。
    """
    # 解析 body
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": JSONRPC_PARSE_ERROR,
                    "message": "parse error: body is not valid JSON",
                },
                "id": None,
            },
            status_code=400,
        )

    if not isinstance(body, dict):
        return _err(None, JSONRPC_INVALID_REQUEST, "request body must be an object")

    # 基础字段校验
    if body.get("jsonrpc") != "2.0":
        return _err(
            body.get("id"),
            JSONRPC_INVALID_REQUEST,
            "jsonrpc field must be '2.0'",
        )
    method = body.get("method")
    if not isinstance(method, str):
        return _err(
            body.get("id"),
            JSONRPC_INVALID_REQUEST,
            "method field must be a string",
        )
    req_id = body.get("id")

    # 未知 method
    if method not in SUPPORTED_METHODS:
        return _err(req_id, JSONRPC_METHOD_NOT_FOUND, f"unknown method: {method}")

    params = body.get("params")

    # 分发
    store = _DEFAULT_STORE
    signed = _verify_optional_jws(request.headers.get("authorization"))

    if method == "SendMessage":
        result, err_code = _handle_send_message(params, store)
    elif method == "ListTasks":
        result, err_code = _handle_list_tasks(params, store)
    elif method == "GetTask":
        result, err_code = _handle_get_task(params, store)
    elif method == "CancelTask":
        result, err_code = _handle_cancel_task(params, store)
    else:  # pragma: no cover - 上面已 guard
        return _err(req_id, JSONRPC_METHOD_NOT_FOUND, f"unknown method: {method}")

    if err_code is None:
        return _ok(req_id, result, signed=signed)

    # A2A_TASK_NOT_FOUND / A2A_INVALID_TRANSITION / INVALID_PARAMS / INTERNAL
    error_message_map = {
        JSONRPC_INVALID_PARAMS: "invalid params",
        JSONRPC_INTERNAL_ERROR: "internal error",
        A2A_TASK_NOT_FOUND: "task not found",
        A2A_INVALID_TRANSITION: "invalid task transition",
    }
    return _err(req_id, err_code, error_message_map.get(err_code, "error"))


__all__ = [
    "router",
    "SUPPORTED_METHODS",
    "LIST_TASKS_MAX_LIMIT",
    "JSONRPC_PARSE_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INTERNAL_ERROR",
    "A2A_TASK_NOT_FOUND",
    "A2A_INVALID_TRANSITION",
    "a2a_jsonrpc_endpoint",
]
