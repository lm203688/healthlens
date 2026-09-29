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
from pydantic import BaseModel, Field

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


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field("2.0", description="JSON-RPC version")
    id: int | str | None = Field(None, description="Request id for correlation")
    method: str = Field(..., description="MCP method: initialize | tools/list | tools/call")
    params: dict = Field(default_factory=dict, description="Method params")


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
async def mcp_rpc(req: JsonRpcRequest, request: Request, response: Response) -> JSONResponse:
    """MCP JSON-RPC 2.0 over HTTP POST.

    Handles:
      - initialize
      - tools/list
      - tools/call
    """
    _check_auth_for_method(req.method, request.headers.get("x-healthlens-mcp-key"))

    try:
        if req.method == "initialize":
            result = _handle_initialize()
        elif req.method == "tools/list":
            result = _handle_tools_list()
        elif req.method == "tools/call":
            result = _handle_tools_call(req.params or {})
        elif req.method == "ping":
            result = {}
        else:
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": req.id,
                    "error": {"code": -32601, "message": f"unknown method: {req.method}"},
                },
                status_code=400,
            )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("mcp rpc handler error")
        return JSONResponse(
            content={
                "jsonrpc": "2.0",
                "id": req.id,
                "error": {"code": -32603, "message": f"internal error: {exc}"},
            },
            status_code=500,
        )

    # Cache-bust: MCP clients may cache responses
    response.headers["Cache-Control"] = "no-store"
    response.headers["Access-Control-Allow-Origin"] = "*"

    return JSONResponse(content={"jsonrpc": "2.0", "id": req.id, "result": result})


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
