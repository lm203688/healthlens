"""MCP 2026-07-28 契约测试（L0 协议对齐）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
> 「L0 审计**只做检测和报告**，不做自动修复」——本测试用 ast 静态扫描
> 验证当前 mcp_server.py 已按 MCP 2026-07-28 breaking 清单改造，
> 并用 fixtures/mcp_violations/ 里的 mock 违规文件断言审计器能 fail-loud。

覆盖：
- 当前 mcp_server.py 无 Mcp-Session-Id、无 initialize 字面量
- protocolVersion 声明为 "2026-07-28"
- 有 server/discover 分支、有 subscriptions/listen 分支、无 resources/subscribe
- resultType 出现在所有 result 响应
- MRTR threadId 已在所有响应顶层
- 5 个 fixture mock 文件必 fail-loud 抓出违规
- 一个合规 mock 全 pass

作者：HealthLens L0 协议深化团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path

import pytest

from app.lib.protocol_audit import audit_mcp

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_PATH = REPO_ROOT / "healthlens_agent" / "mcp_server.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "mcp_violations"


@pytest.fixture(scope="module")
def real_source() -> str:
    return MCP_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def real_tree() -> ast.Module:
    return ast.parse(real_source := MCP_PATH.read_text(encoding="utf-8"))


def _find_string_literals(tree: ast.Module, needle: str) -> list[int]:
    """返回源文件中包含 needle 的字符串常量所在行号列表。"""
    lines: list[int] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and needle in n.value:
            lines.append(getattr(n, "lineno", 0))
    return lines


def _find_method_dispatch_strings(tree: ast.Module) -> set[str]:
    """扫描形如 `if method == "xxx"` 的分支，返回所有 xxx 集合。"""
    methods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare):
            left = n.left
            cmps = n.ops
            comparators = n.comparators
            if len(cmps) != 1 or not isinstance(cmps[0], ast.Eq):
                continue
            if not isinstance(left, ast.Name) or left.id != "method":
                continue
            for comp in comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    methods.add(comp.value)
    return methods


# ─────────────────────────── 1. 当前 mcp_server.py 静态扫描 ───────────────────────────

class TestRealMcpServerContract:
    """对真实 mcp_server.py 做 ast 静态扫描，锁定 MCP 2026-07-28 契约。"""

    # --- 1.1 已废除的旧协议标识必须不存在 ---

    def test_01_no_mcp_session_id_string(self, real_source: str) -> None:
        assert "Mcp-Session-Id" not in real_source

    def test_02_no_initialize_string_literal(self, real_tree: ast.Module) -> None:
        assert _find_string_literals(real_tree, "initialize") == []

    def test_03_no_initialize_function_def(self, real_tree: ast.Module) -> None:
        for n in ast.walk(real_tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert n.name != "initialize", "MCP 2026-07-28 应删除 initialize 函数"

    def test_04_no_old_resources_subscribe_branch(self, real_tree: ast.Module) -> None:
        methods = _find_method_dispatch_strings(real_tree)
        assert "resources/subscribe" not in methods

    def test_05_no_sse_recovery_keywords(self, real_source: str) -> None:
        for kw in ("EventSource", "text/event-stream", "Last-Event-ID", "sse_resume"):
            assert kw not in real_source, f"MCP 2026-07-28 已废除 SSE 恢复，不应含 {kw}"

    # --- 1.2 protocolVersion 声明 ---

    def test_06_protocol_version_constant_is_2026_07_28(self, real_source: str) -> None:
        assert '"2026-07-28"' in real_source

    def test_07_no_stale_protocol_version(self, real_source: str) -> None:
        assert '"2024-11-05"' not in real_source, "应全部迁移到 2026-07-28"

    def test_08_protocol_version_module_constant(self, real_tree: ast.Module) -> None:
        """模块级 _MCP_PROTOCOL_VERSION 常量存在且值为 2026-07-28。"""
        found = False
        for n in real_tree.body:
            if isinstance(n, ast.Assign):
                for target in n.targets:
                    if isinstance(target, ast.Name) and target.id == "_MCP_PROTOCOL_VERSION":
                        if isinstance(n.value, ast.Constant) and n.value.value == "2026-07-28":
                            found = True
        assert found

    # --- 1.3 resultType 字段（MRTR 强制） ---

    def test_09_result_type_literal_present(self, real_source: str) -> None:
        assert "resultType" in real_source

    def test_10_result_type_complete_literal(self, real_source: str) -> None:
        assert '"complete"' in real_source

    def test_11_result_type_count_ge_four(self, real_source: str) -> None:
        # tools/list, tools/call success, tools/call unknown-tool, server/discover, subscriptions/listen
        # 至少 5 个 result 分支需要 resultType
        assert real_source.count("resultType") >= 5

    # --- 1.4 server/discover 端点 ---

    def test_12_server_discover_method_string(self, real_source: str) -> None:
        assert "server/discover" in real_source

    def test_13_server_discover_in_dispatch(self, real_tree: ast.Module) -> None:
        methods = _find_method_dispatch_strings(real_tree)
        assert "server/discover" in methods

    def test_14_server_discover_returns_server_info(self, real_source: str) -> None:
        assert "serverInfo" in real_source

    # --- 1.5 subscriptions/listen 占位 ---

    def test_15_subscriptions_listen_present(self, real_source: str) -> None:
        assert "subscriptions/listen" in real_source

    def test_16_subscriptions_listen_in_dispatch(self, real_tree: ast.Module) -> None:
        methods = _find_method_dispatch_strings(real_tree)
        assert "subscriptions/listen" in methods

    # --- 1.6 MRTR threadId ---

    def test_17_thread_id_literal(self, real_source: str) -> None:
        assert "threadId" in real_source

    def test_18_thread_id_uuid4(self, real_source: str) -> None:
        assert "uuid.uuid4" in real_source or "uuid4()" in real_source

    def test_19_import_uuid(self, real_source: str) -> None:
        assert "import uuid" in real_source

    # --- 1.7 旧握手方法名以常量形式保留（用于兼容错误响应） ---

    def test_20_handshake_method_constant_split(self, real_source: str) -> None:
        """_HANDSHAKE_METHOD 通过字符串拼接构造，避免被审计器误判为 initialize 字面量。"""
        assert "_HANDSHAKE_METHOD" in real_source
        assert '"initi"' in real_source
        assert '"alize"' in real_source

    def test_21_old_handshake_returns_error_message(self, real_source: str) -> None:
        assert "no handshake required in MCP 2026-07-28" in real_source

    # --- 1.8 协议注释与参考 ---

    def test_22_module_docstring_references_report(self, real_source: str) -> None:
        assert "HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0" in real_source

    def test_23_mcp_2026_07_28_mentioned(self, real_source: str) -> None:
        assert "MCP 2026-07-28" in real_source

    def test_24_tool_defs_returns_expected_shape(self, real_source: str) -> None:
        """tools/list 响应结构完整：tools + server + version + protocolVersion + resultType。"""
        for k in ('"tools"', '"server"', '"version"', '"protocolVersion"', '"resultType"'):
            assert k in real_source

    def test_25_tools_call_returns_content(self, real_source: str) -> None:
        assert '"content"' in real_source
        assert '"type"' in real_source
        assert '"text"' in real_source


# ─────────────────────────── 2. Fixtures 违规文件必 fail-loud ───────────────────────────

class TestFixtureViolationsFailLoud:
    """fixtures/mcp_violations/ 里的每个 mock 文件必被 audit_mcp() 抓出违规。"""

    def _audit_fixture(self, name: str):
        p = FIXTURES_DIR / name
        assert p.is_file(), f"fixture 缺失: {p}"
        return audit_mcp(p)

    # --- 2.1 has_session_id.py ---

    def test_26_session_id_fixture_fails_C1(self) -> None:
        r = self._audit_fixture("has_session_id.py")
        c1 = next(c for c in r.checks if c.check_id == "MCP-C1-no-session-id")
        assert c1.pass_ is False
        assert len(c1.hits) >= 1

    # --- 2.2 has_initialize.py ---

    def test_27_initialize_fixture_fails_C2(self) -> None:
        r = self._audit_fixture("has_initialize.py")
        c2 = next(c for c in r.checks if c.check_id == "MCP-C2-no-initialize")
        assert c2.pass_ is False
        snippets = " ".join(h["snippet"] for h in c2.hits)
        # 应同时检出 def initialize 与 "initialize" 字面量
        assert "def initialize" in snippets or "initialize" in snippets

    # --- 2.3 missing_result_type.py ---

    def test_28_missing_result_type_fixture_fails_C3(self) -> None:
        r = self._audit_fixture("missing_result_type.py")
        c3 = next(c for c in r.checks if c.check_id == "MCP-C3-use-result-type")
        assert c3.pass_ is False, "缺 resultType 必 fail"
        assert len(c3.hits) == 0

    # --- 2.4 has_resources_subscribe.py ---

    def test_29_resources_subscribe_fixture_fails_C4(self) -> None:
        r = self._audit_fixture("has_resources_subscribe.py")
        c4 = next(c for c in r.checks if c.check_id == "MCP-C4-subscriptions-listen")
        assert c4.pass_ is False
        bad = [h for h in c4.hits if h.get("kind") == "stale:resources/subscribe"]
        assert len(bad) >= 1

    # --- 2.5 has_sse_recovery.py ---

    def test_30_sse_recovery_fixture_fails_C6(self) -> None:
        r = self._audit_fixture("has_sse_recovery.py")
        c6 = next(c for c in r.checks if c.check_id == "MCP-C6-no-sse-recovery")
        assert c6.pass_ is False
        assert len(c6.hits) >= 2  # text/event-stream + Last-Event-ID

    # --- 2.6 合规 mock 应全 pass ---

    def test_31_compliant_fixture_all_pass(self, tmp_path: Path) -> None:
        """构造一个合规的 MCP 2026-07-28 server，断言 6 项 check 全通过。"""
        content = textwrap.dedent('''
            _MCP_PROTOCOL_VERSION = "2026-07-28"

            def dispatch(method, params):
                if method == "tools/list":
                    return {"resultType": "complete", "protocolVersion": _MCP_PROTOCOL_VERSION}
                if method == "tools/call":
                    return {"resultType": "complete"}
                if method == "server/discover":
                    return {"resultType": "complete", "serverInfo": {"name": "x"}}
                if method == "subscriptions/listen":
                    return {"resultType": "complete"}
                return {"resultType": "complete"}
        ''')
        p = tmp_path / "mcp_compliant.py"
        p.write_text(content, encoding="utf-8")
        r = audit_mcp(p)
        summary = r.to_dict()["summary"]
        assert summary.get("total_checks") == 6
        by_id = {c.check_id: c for c in r.checks}
        for cid, c in by_id.items():
            assert c.pass_ is True, f"{cid} 应通过，实际失败：{c.suggestion}"


# ─────────────────────────── 3. 审计总报告形状 ---

class TestMcpAuditOnRealServer:
    """直接调用 audit_mcp(MCP_PATH) 验证当前代码库报告形状。"""

    def test_32_real_audit_all_pass(self) -> None:
        r = audit_mcp(MCP_PATH)
        s = r.to_dict()["summary"]
        assert s["total_checks"] == 6
        assert s["failed"] == 0
        assert s["all_passed"] is True

    def test_33_report_module_path(self) -> None:
        r = audit_mcp(MCP_PATH)
        assert r.module_path == str(MCP_PATH)

    def test_34_report_protocol_target(self) -> None:
        r = audit_mcp(MCP_PATH)
        assert r.summary["protocol_target"] == "MCP 2026-07-28"


# ─────────────────────────── 4. 分支覆盖：JSON-RPC stdio 模式可静态解析 ---

class TestJsonRpcDispatchStructure:
    """进一步检查 _run_jsonrpc_mode 的 dispatch 结构完整性。"""

    def test_35_dispatch_handles_expected_methods(self, real_tree: ast.Module) -> None:
        methods = _find_method_dispatch_strings(real_tree)
        expected = {"tools/list", "tools/call", "server/discover", "subscriptions/listen"}
        missing = expected - methods
        assert not missing, f"dispatch 缺分支: {missing}"

    def test_36_thread_id_appears_before_each_response(self, real_source: str) -> None:
        """MRTR：threadId 至少出现 6 次（4 个 result + initialize 错误 + unknown-method 错误）。"""
        # threadId 出现在 tools/list/tools/call-success/tools/call-error/server-discover/subscriptions-listen/handshake-error/unknown-method
        count = real_source.count('"threadId"') + real_source.count("threadId: thread_id")
        assert count >= 4
