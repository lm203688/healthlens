"""L0 协议契约测试包（MCP 2026-07-28 + A2A v1.0.1）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
- `test_mcp_contract.py`：对 `healthlens_agent/mcp_server.py` 做 ast 静态扫描
  + 用 audit_mcp() 断言 fixtures/mcp_violations/ 里的违规 mock 必 fail-loud
- `test_a2a_contract.py`：对 `agent-card.json` 做结构契约扫描 + JWS round-trip

所有测试均纯 Python（ast / json / cryptography），无网络/HTTP 调用。
"""
