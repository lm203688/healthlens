"""违规 fixture：tools/call 响应缺必填 result*ype 字段（MRTR 违约）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
用途：契约测试用 audit_mcp() 断言此文件必 fail-loud 检出违规。
"""


def handle_tools_call(params):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            # 缺必填字段（MRTR 强制），此处故意留空
            "content": [{"type": "text", "text": "hello"}],
        },
    }
