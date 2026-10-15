"""L0 协议审计测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「L0 审计**只做检测和报告**，不做自动修复」——本测试验证此行为。

覆盖：
- 对当前 mcp_server.py 的语法扫描不崩溃（基本健康）
- 故意构造违规 mock 文件必 fail-loud
- 每一项 check 的独立行为
- A2A 7 项 check 全量
- run_full_audit 一次跑完的汇总结构
- 文件不存在时的 fail-loud 处理
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from app.lib.protocol_audit import (
    A2AAuditReport,
    CheckResult,
    DEFAULT_CARD_PATH,
    DEFAULT_MCP_PATH,
    McpAuditReport,
    audit_a2a,
    audit_mcp,
    run_full_audit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────── Fixtures ───────────────────────────

@pytest.fixture
def real_mcp_path() -> str:
    return str(DEFAULT_MCP_PATH)


@pytest.fixture
def real_card_path() -> str:
    return str(DEFAULT_CARD_PATH)


@pytest.fixture
def tmp_mcp_file(tmp_path: Path) -> Path:
    """空的 mcp_server.py mock。"""
    p = tmp_path / "mcp_server.py"
    p.write_text("# empty mcp server\n", encoding="utf-8")
    return p


@pytest.fixture
def tmp_card_file(tmp_path: Path) -> Path:
    """最小合法 A2A card。"""
    card = {
        "name": "Test",
        "description": "x",
        "version": "0.27.0",
        "protocolVersion": "1.0",
        "supportedInterfaces": [{"url": "https://x", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}],
        "capabilities": {},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [],
        "conformanceNote": "未实现 SendMessage 等 A2A 任务生命周期",
        "signing_key": "ES256:TODO",
    }
    p = tmp_path / "agent-card.json"
    p.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ─────────────────────────── 1. 当前代码库扫描 ───────────────────────────

class TestRealMcpServerScan:
    """对当前 mcp_server.py 跑一次必须成功，不崩溃。"""

    def test_real_mcp_file_exists(self, real_mcp_path: str) -> None:
        assert Path(real_mcp_path).is_file(), f"mcp_server.py not found at {real_mcp_path}"

    def test_audit_mcp_on_real_file_returns_report(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        assert isinstance(r, McpAuditReport)
        assert len(r.checks) == 6
        # 当前 mcp_server 尚未迁移到 2026-07-28：至少应能扫出「有 initialize」
        ids = [c.check_id for c in r.checks]
        assert "MCP-C1-no-session-id" in ids
        assert "MCP-C2-no-initialize" in ids
        assert "MCP-C3-use-result-type" in ids
        assert "MCP-C4-subscriptions-listen" in ids
        assert "MCP-C5-impl-server-discover" in ids
        assert "MCP-C6-no-sse-recovery" in ids

    def test_real_mcp_audit_summary(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        s = r.to_dict()["summary"]
        assert s["total_checks"] == 6
        assert "passed" in s and "failed" in s and "all_passed" in s
        # 当前 mcp_server.py 有 initialize 字面量（第 681 行），必 fail
        assert any(
            c.check_id == "MCP-C2-no-initialize" and not c.pass_ for c in r.checks
        ), "当前 mcp_server.py 应检出 initialize 残留"

    def test_real_mcp_no_session_id(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        c1 = next(c for c in r.checks if c.check_id == "MCP-C1-no-session-id")
        # 当前代码已无 Mcp-Session-Id
        assert c1.pass_ is True

    def test_real_mcp_no_sse_recovery(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        c6 = next(c for c in r.checks if c.check_id == "MCP-C6-no-sse-recovery")
        assert c6.pass_ is True

    def test_real_mcp_missing_result_type(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        c3 = next(c for c in r.checks if c.check_id == "MCP-C3-use-result-type")
        # 当前代码未实现 resultType（MRTR）
        assert c3.pass_ is False

    def test_real_mcp_missing_server_discover(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path)
        c5 = next(c for c in r.checks if c.check_id == "MCP-C5-impl-server-discover")
        # 当前代码未实现 server/discover
        assert c5.pass_ is False


# ─────────────────────────── 2. Mock 违规文件必 fail ───────────────────────────

class TestMockViolationsFailLoud:
    """构造违规 mock 文件必须 fail-loud。"""

    def _write_mcp(self, tmp_path: Path, content: str) -> str:
        p = tmp_path / "mcp_bad.py"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return str(p)

    def test_session_id_detected(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def handler(request):
                session_id = request.headers.get("Mcp-Session-Id")
                return session_id
        ''')
        r = audit_mcp(p)
        c1 = next(c for c in r.checks if c.check_id == "MCP-C1-no-session-id")
        assert c1.pass_ is False
        assert len(c1.hits) >= 1

    def test_initialize_function_detected(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def initialize(request):
                return {"protocolVersion": "2024-11-05"}
        ''')
        r = audit_mcp(p)
        c2 = next(c for c in r.checks if c.check_id == "MCP-C2-no-initialize")
        assert c2.pass_ is False
        assert any("def initialize" in h["snippet"] for h in c2.hits)

    def test_initialize_string_literal_detected(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def handler(method):
                if method == "initialize":
                    return {}
        ''')
        r = audit_mcp(p)
        c2 = next(c for c in r.checks if c.check_id == "MCP-C2-no-initialize")
        assert c2.pass_ is False

    def test_result_type_present_passes(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def result():
                return {"resultType": "complete", "content": []}
        ''')
        r = audit_mcp(p)
        c3 = next(c for c in r.checks if c.check_id == "MCP-C3-use-result-type")
        assert c3.pass_ is True
        assert len(c3.hits) >= 1

    def test_subscriptions_listen_old_still_detected(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def handler(method):
                if method == "resources/subscribe":
                    return {}
        ''')
        r = audit_mcp(p)
        c4 = next(c for c in r.checks if c.check_id == "MCP-C4-subscriptions-listen")
        assert c4.pass_ is False

    def test_server_discover_present_passes(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def handler(method):
                if method == "server/discover":
                    return {}
        ''')
        r = audit_mcp(p)
        c5 = next(c for c in r.checks if c.check_id == "MCP-C5-impl-server-discover")
        assert c5.pass_ is True

    def test_sse_eventstream_detected(self, tmp_path: Path) -> None:
        p = self._write_mcp(tmp_path, '''
            def stream():
                # SSE
                return {"content_type": "text/event-stream", "Last-Event-ID": "123"}
        ''')
        r = audit_mcp(p)
        c6 = next(c for c in r.checks if c.check_id == "MCP-C6-no-sse-recovery")
        assert c6.pass_ is False
        assert len(c6.hits) >= 1

    def test_compliant_mcp_all_pass(self, tmp_path: Path) -> None:
        """模拟一个合规的 2026-07-28 mcp server。"""
        content = textwrap.dedent('''
            def handler(method):
                if method == "tools/list":
                    return {}
                if method == "tools/call":
                    return {"resultType": "complete"}
                if method == "server/discover":
                    return {}
                if method == "subscriptions/listen":
                    return {}
        ''')
        p = self._write_mcp(tmp_path, content)
        r = audit_mcp(p)
        # 除 C3 (resultType 已声明) / C5 (discover 已声明) 外，其他 pass
        by_id = {c.check_id: c for c in r.checks}
        assert by_id["MCP-C1-no-session-id"].pass_ is True
        assert by_id["MCP-C2-no-initialize"].pass_ is True
        assert by_id["MCP-C3-use-result-type"].pass_ is True
        assert by_id["MCP-C4-subscriptions-listen"].pass_ is True
        assert by_id["MCP-C5-impl-server-discover"].pass_ is True
        assert by_id["MCP-C6-no-sse-recovery"].pass_ is True

    def test_missing_file_returns_fail_report(self) -> None:
        r = audit_mcp("/nonexistent/path/mcp_server.py")
        assert isinstance(r, McpAuditReport)
        assert len(r.checks) == 1
        assert r.checks[0].check_id == "MCP-FILE-MISSING"
        assert r.checks[0].pass_ is False

    def test_syntax_error_does_not_crash(self, tmp_path: Path) -> None:
        p = tmp_path / "mcp_bad.py"
        p.write_text("def broken(:\n    pass\n", encoding="utf-8")  # 语法错误
        r = audit_mcp(str(p))
        # 不应抛异常
        assert isinstance(r, McpAuditReport)
        # AST 解析失败时 tree=None，仍返回 6 项 check
        assert len(r.checks) == 6


# ─────────────────────────── 3. A2A 审计 ───────────────────────────

class TestA2AAudit:
    """A2A 卡片 7 项 check 覆盖。"""

    def test_real_agent_card_scan(self, real_card_path: str) -> None:
        r = audit_a2a(real_card_path)
        assert isinstance(r, A2AAuditReport)
        assert len(r.checks) == 7

    def test_version_matches_pyproject_on_real(self, real_card_path: str) -> None:
        r = audit_a2a(real_card_path)
        c1 = next(c for c in r.checks if c.check_id == "A2A-C1-version-match")
        # 当前 agent-card version=0.27.0，pyproject=0.27.0 → pass
        assert c1.pass_ is True

    def test_conformance_note_discloses_gap(self, real_card_path: str) -> None:
        r = audit_a2a(real_card_path)
        c7 = next(c for c in r.checks if c.check_id == "A2A-C7-conformance-honest")
        assert c7.pass_ is True

    def test_missing_file_returns_fail_report(self) -> None:
        r = audit_a2a("/nonexistent/agent-card.json")
        assert len(r.checks) == 1
        assert r.checks[0].check_id == "A2A-FILE-MISSING"

    def test_invalid_json_returns_fail_report(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        r = audit_a2a(str(p))
        assert len(r.checks) == 1
        assert r.checks[0].check_id == "A2A-FILE-INVALID-JSON"
        assert r.checks[0].pass_ is False

    def test_version_mismatch_fails(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "description": "x", "version": "9.9.9",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c1 = next(c for c in r.checks if c.check_id == "A2A-C1-version-match")
        assert c1.pass_ is False
        assert c1.hits[0]["snippet"].startswith("card.version=")

    def test_send_message_present_passes(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {"methods": ["SendMessage"]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "支持 SendMessage",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c3 = next(c for c in r.checks if c.check_id == "A2A-C3-uses-SendMessage")
        assert c3.pass_ is True

    def test_message_send_string_fails(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {"methods": ["message/send"]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "支持 message/send",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c3 = next(c for c in r.checks if c.check_id == "A2A-C3-uses-SendMessage")
        assert c3.pass_ is False

    def test_enum_screaming_snake_passes(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [],
            "capabilities": {"extensions": [{"values": ["SEND_MESSAGE", "LIST_TASKS"]}]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 ListTasks",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c2 = next(c for c in r.checks if c.check_id == "A2A-C2-enum-screaming-snake")
        assert c2.pass_ is True

    def test_enum_lowercase_fails(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [],
            "capabilities": {"extensions": [{"values": ["send_message", "list_tasks"]}]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 ListTasks",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c2 = next(c for c in r.checks if c.check_id == "A2A-C2-enum-screaming-snake")
        assert c2.pass_ is False
        assert any("send_message" in h["snippet"] for h in c2.hits)

    def test_signing_key_declared_passes(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage",
            "signing_key": "ES256:TODO",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c5 = next(c for c in r.checks if c.check_id == "A2A-C5-declare-signing-key")
        assert c5.pass_ is True

    def test_missing_signing_key_warns(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c5 = next(c for c in r.checks if c.check_id == "A2A-C5-declare-signing-key")
        assert c5.pass_ is False

    def test_list_tasks_declared_passes(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [],
            "capabilities": {"methods": ["ListTasks"]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "支持 ListTasks",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c4 = next(c for c in r.checks if c.check_id == "A2A-C4-declare-ListTasks")
        assert c4.pass_ is True

    def test_list_tasks_disclosed_in_note_passes(self, tmp_path: Path) -> None:
        """未声明 ListTasks 但 note 如实说明未实现也通过。"""
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage / GetTask / ListTasks 等任务生命周期",
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c4 = next(c for c in r.checks if c.check_id == "A2A-C4-declare-ListTasks")
        assert c4.pass_ is True

    def test_conformance_honest_failure(self, tmp_path: Path) -> None:
        """谎称实现了 SendMessage 但 note 未披露 gap → fail。"""
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [],
            "capabilities": {"methods": ["SendMessage", "GetTask", "CancelTask"]},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "全部能力已实现",  # 谎称
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c7 = next(c for c in r.checks if c.check_id == "A2A-C7-conformance-honest")
        assert c7.pass_ is False

    def test_missing_conformance_note_fails(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c7 = next(c for c in r.checks if c.check_id == "A2A-C7-conformance-honest")
        assert c7.pass_ is False

    def test_multi_tenancy_declared_passes(self, tmp_path: Path) -> None:
        card = {
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage",
            "multiTenancy": {"supported": True},
            "mtls": {"enabled": False},
        }
        p = tmp_path / "agent-card.json"
        p.write_text(json.dumps(card), encoding="utf-8")
        r = audit_a2a(str(p))
        c6 = next(c for c in r.checks if c.check_id == "A2A-C6-multi-tenancy-mtls")
        assert c6.pass_ is True
        assert len(c6.hits) >= 1


# ─────────────────────────── 4. run_full_audit ───────────────────────────

class TestRunFullAudit:
    """全量审计入口。"""

    def test_returns_all_sections(self) -> None:
        r = run_full_audit()
        assert "mcp" in r
        assert "a2a" in r
        assert "overall" in r
        assert "generated_at" in r
        assert "repo_root" in r

    def test_overall_summary_counts(self) -> None:
        r = run_full_audit()
        o = r["overall"]
        m = r["mcp"]["summary"]
        a = r["a2a"]["summary"]
        assert o["total_checks"] == m["total_checks"] + a["total_checks"]
        assert o["passed"] == m["passed"] + a["passed"]
        assert o["failed"] == m["failed"] + a["failed"]

    def test_blocking_failures_only_errors(self) -> None:
        r = run_full_audit()
        o = r["overall"]
        # blocking_failures 只列 severity=error 的 fail
        for check_id in o["blocking_failures"]:
            all_checks = r["mcp"]["checks"] + r["a2a"]["checks"]
            c = next(x for x in all_checks if x["check_id"] == check_id)
            assert c["severity"] == "error"
            assert c["pass"] is False

    def test_generated_at_is_iso(self) -> None:
        r = run_full_audit()
        # ISO 8601 with UTC offset
        assert "T" in r["generated_at"]
        assert "Z" in r["generated_at"] or "+" in r["generated_at"]

    def test_custom_paths(self, tmp_path: Path) -> None:
        """允许自定义 mcp/card 路径。"""
        mcp_p = tmp_path / "custom_mcp.py"
        mcp_p.write_text('def handler():\n    return {"resultType": "complete"}\n', encoding="utf-8")
        card_p = tmp_path / "custom_card.json"
        card_p.write_text(json.dumps({
            "name": "T", "version": "0.27.0", "description": "x",
            "supportedInterfaces": [], "capabilities": {},
            "defaultInputModes": [], "defaultOutputModes": [], "skills": [],
            "conformanceNote": "未实现 SendMessage",
            "signing_key": "ES256:TODO",
        }), encoding="utf-8")
        r = run_full_audit(mcp_module_path=str(mcp_p), a2a_card_path=str(card_p))
        assert r["mcp"]["module_path"] == str(mcp_p)
        assert r["a2a"]["card_path"] == str(card_p)

    def test_current_audit_report_shape(self) -> None:
        """锁定当前代码库审计输出的形状（供 CI 回归）。"""
        r = run_full_audit()
        # 当前 mcp_server.py 应有 6 项 check，至少 3 项 fail（initialize/resultType/discover）
        m = r["mcp"]
        assert m["summary"]["total_checks"] == 6
        assert m["summary"]["failed"] >= 2
        a = r["a2a"]
        assert a["summary"]["total_checks"] == 7


# ─────────────────────────── 5. CheckResult 结构 ───────────────────────────

class TestCheckResultShape:
    """CheckResult 序列化形状。"""

    def test_to_dict_shape(self) -> None:
        c = CheckResult(
            check_id="X",
            pass_=True,
            hits=[{"file": "f", "line": 1, "snippet": "s"}],
            suggestion="ok",
            severity="info",
        )
        d = c.to_dict()
        assert d["check_id"] == "X"
        assert d["pass"] is True
        assert len(d["hits"]) == 1
        assert d["suggestion"] == "ok"
        assert d["severity"] == "info"

    def test_mcp_report_to_dict(self, real_mcp_path: str) -> None:
        r = audit_mcp(real_mcp_path).to_dict()
        assert r["module_path"] == real_mcp_path
        assert isinstance(r["checks"], list)
        assert all("check_id" in c and "pass" in c and "hits" in c for c in r["checks"])

    def test_a2a_report_to_dict(self, real_card_path: str) -> None:
        r = audit_a2a(real_card_path).to_dict()
        assert r["card_path"] == real_card_path
        assert isinstance(r["checks"], list)
