"""违规 fixture：含 Mcp-Session-Id 字符串（MCP 2026-07-28 已废除）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
用途：契约测试用 audit_mcp() 断言此文件必 fail-loud 检出违规。
"""
SESSION_ID_HEADER = "Mcp-Session-Id"


def handle(request_headers):
    sid = request_headers.get(SESSION_ID_HEADER)
    return {"session": sid}
