"""违规 fixture：仍在使用旧 resources/subscribe 端点。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
用途：契约测试用 audit_mcp() 断言此文件必 fail-loud 检出违规。
"""


def dispatch(method):
    if method == "resources/subscribe":
        return {"subscriptionId": "abc123"}
    if method == "server/discover":
        return {"resultType": "complete", "serverInfo": {"name": "x"}}
    return {}
