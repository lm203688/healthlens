"""违规 fixture：含 initialize 握手函数 + "initialize" 字面量。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
用途：契约测试用 audit_mcp() 断言此文件必 fail-loud 检出违规。
"""


def initialize(request):
    """旧版 MCP 2024-11-05 握手：返回 protocolVersion 与 serverInfo。"""
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "legacy-server", "version": "1.0"},
    }


def dispatch(method):
    if method == "initialize":
        return initialize(None)
    return {}
