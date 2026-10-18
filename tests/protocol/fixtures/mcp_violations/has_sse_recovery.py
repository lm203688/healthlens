"""违规 fixture：含 SSE 断点续传逻辑（MCP 2026-07-28 已砍掉可恢复 SSE）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
用途：契约测试用 audit_mcp() 断言此文件必 fail-loud 检出违规。
"""


def stream_event():
    return {
        "content_type": "text/event-stream",
        "Last-Event-ID": "last_event_id",
        "resultType": "complete",
    }


def reconnect(last_id):
    """SSE 断点续传——2026-07-28 已废除。"""
    return {"resume_from": last_id}
