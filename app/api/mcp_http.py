"""
app/api/mcp_http.py — HealthLens MCP Server over HTTP

Exposes the same tool registry as `healthlens_agent.mcp_server` via JSON-RPC 2.0
over HTTP POST. This lets foreign MCP clients (Claude Desktop, Cursor, Cline,
ChatGPT Custom GPTs, hosted agents like GrokBot, Muse, Coze, Dify) connect
with a single URL instead of requiring a local `pip install`.

Protocol: MCP 2024-11-05, JSON-RPC 2.0 request/response over HTTP POST
(single request → single response). Not SSE/Streamable-HTTP — kept simple
because all major clients support this variant.

Endpoint: POST /api/v1/mcp
Content-Type: application/json
Body: {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
Response: {"jsonrpc": "2.0", "result": {...}, "id": 1}

Auth:
  - L1/L2 tools: no auth required (public wellness knowledge)
  - L3 tools (personalized): requires HL_MCP_EXPOSE_PRIVATE=1 in server env
    AND an X-HealthLens-MCP-Key header matching HL_MCP_HTTP_KEY when set

Rate limit: per-IP via slowapi limiter (inherited from app.state.limiter)
"""
from __future__ import annotations

import json
import logging
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from healthlens_agent.mcp_server import (
    _SERVER_VERSION,
    _EXPOSE_PRIVATE,
    _active_tools,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp-http"])

# Optional bearer key for L3-when-enabled. If unset, L3 is open (dev mode).
_HTTP_KEY = os.environ.get("HL_MCP_HTTP_KEY", "")

_START_TS = time.time()


# We intentionally do NOT declare a strict JSON-RPC Pydantic model here: the MCP
# protocol also sends "notifications/*" messages without an `id` field and
# supports JSON-RPC 2.0 batch requests (a list of envelopes), both of which a
# fixed envelope schema would reject. We parse via `request.json()` and
# dispatch each envelope manually in `_dispatch_one`.


def _tool_defs() -> list[dict]:
    """MCP-spec tools array: each entry has name/description/inputSchema."""
    tools = _active_tools()
    return [
        {
            "name": name,
            "description": spec["description"],
            "inputSchema": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in spec["args"]},
            },
        }
        for name, spec in tools.items()
    ]


def _handle_initialize() -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "healthlens-mcp", "version": _SERVER_VERSION},
        "capabilities": {"tools": {"listChanged": False}},
        "instructions": (
            "HealthLens wellness knowledge tools. L1 (content) and L2 "
            "(general knowledge) are public-safe. L3 (personalized reasoning) "
            "is gated by HL_MCP_EXPOSE_PRIVATE on the server side."
        ),
    }


def _handle_tools_list() -> dict:
    return {
        "tools": _tool_defs(),
        "server": "healthlens-mcp",
        "version": _SERVER_VERSION,
        "private_exposed": _EXPOSE_PRIVATE,
    }


def _handle_tools_call(params: dict) -> dict:
    tools = _active_tools()
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name not in tools:
        raise HTTPException(
            status_code=400,
            detail={"jsonrpc_error": -32602, "message": f"unknown tool: {tool_name}"},
        )

    try:
        result = tools[tool_name]["handler"](**args)
    except TypeError as exc:
        raise HTTPException(
            status_code=400,
            detail={"jsonrpc_error": -32602, "message": f"invalid arguments: {exc}"},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("tool call failed: %s", tool_name)
        raise HTTPException(
            status_code=500,
            detail={"jsonrpc_error": -32603, "message": f"tool execution failed: {exc}"},
        )

    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
    }


def _check_auth_for_method(method: str, mcp_key: str | None) -> None:
    """Auth gate: L3 tools require key when HL_MCP_HTTP_KEY is set."""
    if not _HTTP_KEY:
        return  # dev mode: no key required
    # tools/call with an L3 tool needs the key
    # Other methods (initialize, tools/list, L1/L2 tools/call) pass through
    if method == "tools/call":
        # We can't cheaply know which tool without parsing params; be strict
        # when L3 is exposed.
        if _EXPOSE_PRIVATE and (mcp_key or "") != _HTTP_KEY:
            raise HTTPException(
                status_code=401,
                detail="X-HealthLens-MCP-Key required for L3 tools",
            )


@router.post("")
async def mcp_rpc(request: Request, response: Response):
    """MCP JSON-RPC 2.0 over HTTP POST.

    Handles:
      - initialize
      - tools/list
      - tools/call
      - ping
      - notifications/* (fire-and-forget, returns 202 No Content)
    Also handles JSON-RPC batch requests (a list of envelopes).
    """
    response.headers["Cache-Control"] = "no-store"
    response.headers["Access-Control-Allow-Origin"] = "*"

    try:
        raw = await request.json()
    except Exception as exc:
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {exc}"},
            },
            status_code=400,
        )

    mcp_key = request.headers.get("x-healthlens-mcp-key")

    # Batch: list of envelopes. JSON-RPC 2.0 §6.4.
    if isinstance(raw, list):
        bodies = []
        for env in raw:
            if not isinstance(env, dict):
                continue
            if _is_notification(env):
                continue  # notifications have no response
            bodies.append(_dispatch_one(env, mcp_key))
        return JSONResponse(content=bodies, status_code=200)

    if not isinstance(raw, dict):
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "invalid request envelope"},
            },
            status_code=400,
        )

    if _is_notification(raw):
        return JSONResponse(content=None, status_code=202)

    body = _dispatch_one(raw, mcp_key)
    status = body.get("_status", 200)
    body.pop("_status", None)
    return JSONResponse(content=body, status_code=status)


def _is_notification(env: dict) -> bool:
    """JSON-RPC 2.0 notification: method starting with 'notifications/' or no 'id' field."""
    if not isinstance(env, dict):
        return False
    method = env.get("method", "")
    if method.startswith("notifications/"):
        return True
    return "id" not in env


def _dispatch_one(env: dict, mcp_key: str | None) -> dict:
    """Return a plain dict — the JSON-RPC response envelope.

    The dict may contain a private `_status` key that the caller reads and pops
    to set the HTTP status. This lets batch mode collect multiple envelopes
    (JSONResponse objects cannot be nested inside another response body).
    """
    req_id = env.get("id")
    method = env.get("method", "")

    try:
        _check_auth_for_method(method, mcp_key)
    except HTTPException:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32001, "message": "auth required"},
            "_status": 401,
        }

    try:
        if method == "initialize":
            result = _handle_initialize()
        elif method == "tools/list":
            result = _handle_tools_list()
        elif method == "tools/call":
            result = _handle_tools_call(env.get("params") or {})
        elif method == "ping":
            result = {}
        else:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
                "_status": 400,
            }
    except HTTPException as exc:
        # Re-wrap as JSON-RPC error envelope (FastAPI's default detail shape
        # lacks jsonrpc/id fields that MCP clients expect).
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": detail.get("jsonrpc_error", -32603),
                "message": detail.get("message", str(exc.detail)),
            },
            "_status": exc.status_code,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("mcp rpc handler error")
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32603, "message": str(exc)},
            "_status": 500,
        }

    return {"jsonrpc": "2.0", "id": req_id, "result": result}


@router.get("/tools")
async def mcp_tools_browser() -> JSONResponse:
    """Human-readable tool list for quick verification / MCP Registry preview."""
    return JSONResponse(
        content={
            "server": "healthlens-mcp",
            "version": _SERVER_VERSION,
            "transport": "http-post-jsonrpc",
            "endpoint": "/api/v1/mcp",
            "uptime_seconds": round(time.time() - _START_TS, 1),
            "private_exposed": _EXPOSE_PRIVATE,
            "tools": _tool_defs(),
        }
    )


@router.get("")
async def mcp_endpoint_info() -> JSONResponse:
    """MCP server info at the endpoint root (for discovery tools)."""
    return JSONResponse(
        content={
            "name": "healthlens-mcp",
            "version": _SERVER_VERSION,
            "transport": "http-post-jsonrpc",
            "protocolVersion": "2024-11-05",
            "endpoint": "/api/v1/mcp",
            "methods": ["initialize", "tools/list", "tools/call", "ping"],
            "private_exposed": _EXPOSE_PRIVATE,
            "docs": "https://github.com/lm203688/healthlens/tree/main/mcp-server",
        }
    )
