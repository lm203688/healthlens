"""MCP 2026-07-28 / A2A v1.0.1 契约审计器（L0 协议对齐层）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「L0 审计**只做检测和报告**，不做自动修复」——本模块定位。

定位：
- **静态 AST 审计**：用 Python `ast` 模块扫描源代码（不改写），
  报告 MCP 2026-07-28 / A2A v1.0.1 契约合规状态。
- **fail-loud 输出**：每项 check 返回 `{check_id, pass, hits, suggestion}`；
  CI 消费 `run_full_audit()` 的 JSON 结构。
- **只读**：本模块绝不修改源代码，任何修复决策留给工程师。

MCP 2026-07-28 硬性 breaking 检查项（对应 6 项）：
1. `Mcp-Session-Id` 字符串残留（已废除，无状态化）
2. `initialize` 方法/端点残留（无状态握手已废除）
3. `resultType` 字段使用（MRTR 要求）
4. `resources/subscribe` 是否已改为 `subscriptions/listen`
5. `server/discover` 是否已实现
6. SSE 恢复逻辑是否已移除（2026-07-28 已砍掉可恢复 SSE）

A2A v1.0.1 检查项（7 项）：
1. version 与 pyproject.toml 一致
2. enum 值 SCREAMING_SNAKE_CASE
3. 使用 `SendMessage` 而非 `message/send`
4. 是否声明 `ListTasks`
5. 是否声明 JWS `signing_key`
6. 是否有 `multiTenancy` / `mtls` 字段
7. `conformanceNote` 如实（不谎称实现了 ListTasks）

Wellness 平台术语纪律：本模块只做静态扫描，不做业务判断。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─────────────────────────── 常量 ───────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MCP_PATH = REPO_ROOT / "healthlens_agent" / "mcp_server.py"
DEFAULT_CARD_PATH = REPO_ROOT / "agent-card.json"
DEFAULT_PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# SCREAMING_SNAKE_CASE：大写字母/数字/下划线，首字符大写字母
_ENUM_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


# ─────────────────────────── 数据结构 ───────────────────────────

@dataclass
class CheckResult:
    """单项检查的结果。"""

    check_id: str
    pass_: bool
    hits: list[dict[str, Any]] = field(default_factory=list)
    suggestion: str = ""
    severity: str = "error"  # "error" | "warn" | "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "pass": self.pass_,
            "hits": self.hits,
            "suggestion": self.suggestion,
            "severity": self.severity,
        }


@dataclass
class McpAuditReport:
    """MCP 审计总报告。"""

    module_path: str
    checks: list[CheckResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        passed = sum(1 for c in self.checks if c.pass_)
        total = len(self.checks)
        return {
            "module_path": self.module_path,
            "summary": {
                "total_checks": total,
                "passed": passed,
                "failed": total - passed,
                "all_passed": passed == total,
            } | self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class A2AAuditReport:
    """A2A 审计总报告。"""

    card_path: str
    checks: list[CheckResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        passed = sum(1 for c in self.checks if c.pass_)
        total = len(self.checks)
        return {
            "card_path": self.card_path,
            "summary": {
                "total_checks": total,
                "passed": passed,
                "failed": total - passed,
                "all_passed": passed == total,
            } | self.summary,
            "checks": [c.to_dict() for c in self.checks],
        }


# ─────────────────────────── AST 扫描工具 ───────────────────────────

def _file_source(path: Path) -> str:
    """读取源文件（utf-8）。"""
    return path.read_text(encoding="utf-8")


def _split_line_hits(source: str, needle: str) -> list[dict[str, Any]]:
    """按行扫描字符串命中（用于检测残留标识符）。"""
    hits: list[dict[str, Any]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if needle in line:
            # 截取包含 needle 的 60 字符片段，避免过长
            idx = line.index(needle)
            start = max(0, idx - 20)
            end = min(len(line), idx + 40)
            hits.append({
                "file": str(source),  # 占位，由调用方覆盖
                "line": i,
                "snippet": line.strip()[start:end] or line.strip(),
            })
    return hits


def _parse_module(path: Path) -> ast.Module | None:
    """用 ast.parse 解析模块；语法错误返回 None。"""
    src = _file_source(path)
    try:
        return ast.parse(src, filename=str(path))
    except SyntaxError:
        return None


def _walk_assign_strings(tree: ast.AST) -> list[ast.Constant]:
    """收集所有 ast.Constant 字符串常量（含 Call 里的字面量参数）。"""
    out: list[ast.Constant] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node)
    return out


def _walk_function_defs(tree: ast.AST) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _walk_call_names(tree: ast.AST) -> list[str]:
    """收集所有被调用的函数/方法名（用于 detect `initialize(...)`）。"""
    out: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.append(f.id)
            elif isinstance(f, ast.Attribute):
                out.append(f.attr)
    return out


# ─────────────────────────── MCP 审计 ───────────────────────────

def _mcp_check_session_id(module_path: Path, source: str) -> CheckResult:
    """MCP-C1: 无残留 `Mcp-Session-Id` 字符串（2026-07-28 废除）。"""
    hits = _split_line_hits(source, "Mcp-Session-Id")
    return CheckResult(
        check_id="MCP-C1-no-session-id",
        pass_=not hits,
        hits=hits,
        suggestion="删除所有 `Mcp-Session-Id` 字符串；MCP 2026-07-28 已全无状态。"
        if hits else "OK：无 session id 残留。",
    )


def _mcp_check_initialize(module_path: Path, tree: ast.Module | None, source: str) -> CheckResult:
    """MCP-C2: 无 `initialize` 端点/方法（2026-07-28 废除握手）。"""
    hits: list[dict[str, Any]] = []
    if tree is not None:
        for n in ast.walk(tree):
            # 函数名是 initialize
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "initialize":
                hits.append({
                    "file": str(module_path),
                    "line": getattr(n, "lineno", 0),
                    "snippet": f"def initialize ...",
                })
            # 字符串字面量 "initialize"（例如 `method == "initialize"`）
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.strip() == "initialize":
                hits.append({
                    "file": str(module_path),
                    "line": getattr(n, "lineno", 0),
                    "snippet": 'literal "initialize"',
                })
    return CheckResult(
        check_id="MCP-C2-no-initialize",
        pass_=not hits,
        hits=hits,
        suggestion="删除 initialize 握手端点与字面量；MCP 2026-07-28 无需握手。"
        if hits else "OK：无 initialize 端点。",
    )


def _mcp_check_result_type(module_path: Path, tree: ast.Module | None, source: str) -> CheckResult:
    """MCP-C3: 使用 `resultType` 字段（MRTR 要求 complete | input_required）。

    2026-07-28 规范要求每个 tool result 都带 `resultType`；当前实现未带，
    故 check pass 条件为「找到 resultType 字面量」。
    """
    hits: list[dict[str, Any]] = []
    if tree is not None:
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and "resultType" in n.value:
                hits.append({
                    "file": str(module_path),
                    "line": getattr(n, "lineno", 0),
                    "snippet": '"resultType"',
                })
    # 补充：直接文本扫描（可能拼写在 f-string 里被 AST 拆散）
    for h in _split_line_hits(source, "resultType"):
        if not any(x["line"] == h["line"] for x in hits):
            h["file"] = str(module_path)
            hits.append(h)
    return CheckResult(
        check_id="MCP-C3-use-result-type",
        pass_=bool(hits),
        hits=hits,
        suggestion="为每个 tools/call 响应的 result 对象添加 `resultType: complete|input_required`（MRTR 强制）。"
        if not hits else "OK：使用 resultType 字段。",
    )


def _mcp_check_subscriptions_listen(module_path: Path, tree: ast.Module | None, source: str) -> CheckResult:
    """MCP-C4: `resources/subscribe` 是否已改为 `subscriptions/listen`。

    通过条件：无 `resources/subscribe` 字符串（无论是否加了新的 listen）。
    额外报告：是否新增了 `subscriptions/listen`。
    """
    bad_hits = _split_line_hits(source, "resources/subscribe")
    listen_hits = _split_line_hits(source, "subscriptions/listen")
    return CheckResult(
        check_id="MCP-C4-subscriptions-listen",
        pass_=not bad_hits,
        hits=[
            {**h, "file": str(module_path), "kind": "stale:resources/subscribe"} for h in bad_hits
        ] + [
            {**h, "file": str(module_path), "kind": "new:subscriptions/listen"} for h in listen_hits
        ],
        suggestion="删除所有 `resources/subscribe`；MCP 2026-07-28 用 `subscriptions/listen`。"
        if bad_hits else "OK：无 resources/subscribe 残留。",
    )


def _mcp_check_server_discover(module_path: Path, tree: ast.Module | None, source: str) -> CheckResult:
    """MCP-C5: `server/discover` 是否已实现（2026-07-28 新增）。"""
    hits: list[dict[str, Any]] = []
    for h in _split_line_hits(source, "server/discover"):
        h["file"] = str(module_path)
        hits.append(h)
    # 也检测函数名 `discover`
    if tree is not None:
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "discover":
                hits.append({
                    "file": str(module_path),
                    "line": getattr(n, "lineno", 0),
                    "snippet": "def discover ...",
                })
    return CheckResult(
        check_id="MCP-C5-impl-server-discover",
        pass_=bool(hits),
        hits=hits,
        suggestion="实现 `server/discover` 端点（MCP 2026-07-28 新增，允许客户端发现能力元数据）。"
        if not hits else "OK：server/discover 已实现。",
    )


def _mcp_check_no_sse_reconnect(module_path: Path, source: str) -> CheckResult:
    """MCP-C6: SSE 恢复逻辑已移除（2026-07-28 砍掉可恢复 SSE）。"""
    # 搜索常见 SSE 相关关键字
    patterns = [
        ("EventSource", "EventSource"),
        ("text/event-stream", "text/event-stream"),
        ("Last-Event-ID", "Last-Event-ID"),
        ("sse_resume", "sse_resume"),
        ("reconnect_to_sse", "reconnect_to_sse"),
    ]
    hits: list[dict[str, Any]] = []
    for label, needle in patterns:
        for h in _split_line_hits(source, needle):
            h["file"] = str(module_path)
            h["kind"] = label
            hits.append(h)
    return CheckResult(
        check_id="MCP-C6-no-sse-recovery",
        pass_=not hits,
        hits=hits,
        suggestion="删除 SSE 恢复逻辑（Last-Event-ID 断点续传）；MCP 2026-07-28 已移除。"
        if hits else "OK：无 SSE 恢复逻辑残留。",
    )


def audit_mcp(module_path: str | Path | None = None) -> McpAuditReport:
    """对 mcp_server.py 做全量审计。

    Args:
        module_path: MCP server 源文件路径（默认 REPO_ROOT/healthlens_agent/mcp_server.py）

    Returns:
        McpAuditReport，含 6 项 check 结果。
    """
    p = Path(module_path) if module_path else DEFAULT_MCP_PATH
    if not p.is_file():
        report = McpAuditReport(
            module_path=str(p),
            checks=[CheckResult(
                check_id="MCP-FILE-MISSING",
                pass_=False,
                hits=[],
                suggestion=f"文件不存在: {p}",
                severity="error",
            )],
            summary={"error": "file-missing"},
        )
        return report

    source = _file_source(p)
    tree = _parse_module(p)

    checks = [
        _mcp_check_session_id(p, source),
        _mcp_check_initialize(p, tree, source),
        _mcp_check_result_type(p, tree, source),
        _mcp_check_subscriptions_listen(p, tree, source),
        _mcp_check_server_discover(p, tree, source),
        _mcp_check_no_sse_reconnect(p, source),
    ]

    report = McpAuditReport(module_path=str(p), checks=checks)
    report.summary["protocol_target"] = "MCP 2026-07-28"
    return report


# ─────────────────────────── A2A 审计 ───────────────────────────

def _pyproject_version(pyproject_path: Path) -> str:
    """读取 pyproject.toml 的 [project].version。"""
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return ""
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return str(data.get("project", {}).get("version", ""))
    except Exception:  # noqa: BLE001
        return ""


def _a2a_check_version(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C1: version 与 pyproject.toml 一致。"""
    card_version = str(card.get("version", ""))
    pyproject_v = _pyproject_version(DEFAULT_PYPROJECT_PATH)
    ok = bool(card_version) and bool(pyproject_v) and card_version == pyproject_v
    return CheckResult(
        check_id="A2A-C1-version-match",
        pass_=ok,
        hits=[] if ok else [{
            "file": str(card_path),
            "line": 0,
            "snippet": f"card.version={card_version!r} pyproject.version={pyproject_v!r}",
        }],
        suggestion="卡片版本必须与 pyproject.toml 单一真源一致。" if not ok else "OK：版本一致。",
    )


def _iter_enum_candidates(obj: Any, path: str = "") -> list[tuple[str, str]]:
    """递归找 enum 候选：字典的 `values` / `allowed` / `enum` 键。

    递归进入 dict / list，以便深入 `capabilities.extensions[0].values` 这类
    多层嵌套结构。
    """
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if k in ("values", "allowed", "enum") and isinstance(v, list):
                for i, x in enumerate(v):
                    if isinstance(x, str):
                        out.append((f"{p}[{i}]", x))
            out.extend(_iter_enum_candidates(v, p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            out.extend(_iter_enum_candidates(item, f"{path}[{i}]"))
    return out


def _a2a_check_enum_case(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C2: enum 值必须 SCREAMING_SNAKE_CASE。"""
    bad_hits: list[dict[str, Any]] = []
    for p, val in _iter_enum_candidates(card):
        if not _ENUM_PATTERN.match(val):
            bad_hits.append({
                "file": str(card_path),
                "line": 0,
                "snippet": f"{p}: {val!r}",
            })
    return CheckResult(
        check_id="A2A-C2-enum-screaming-snake",
        pass_=not bad_hits,
        hits=bad_hits,
        suggestion="enum 值改为 SCREAMING_SNAKE_CASE（如 SEND_MESSAGE，非 send_message）。"
        if bad_hits else "OK：enum 命名合规（或未声明 enum）。",
    )


def _a2a_check_send_message(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C3: 使用 `SendMessage` 而非 `message/send`。"""
    raw = json.dumps(card, ensure_ascii=False)
    hits: list[dict[str, Any]] = []
    if "message/send" in raw:
        hits.append({
            "file": str(card_path),
            "line": 0,
            "snippet": 'found "message/send" (should use "SendMessage")',
        })
    has_sendmessage = "SendMessage" in raw
    return CheckResult(
        check_id="A2A-C3-uses-SendMessage",
        pass_=not hits,
        hits=hits,
        suggestion="把 method 名 `message/send` 改为 `SendMessage`。"
        if hits else "OK：无 message/send 残留。" + ("（未声明 SendMessage，但也不违规）" if not has_sendmessage else "（已声明 SendMessage）"),
    )


def _a2a_check_list_tasks(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C4: 是否声明 `ListTasks`（新 API）。

    通过条件：声明了 ListTasks（或明确在 conformanceNote 中未声明也未提及）。
    未声明不视为 fail（旧兼容），只 warn。
    """
    raw = json.dumps(card, ensure_ascii=False)
    hits: list[dict[str, Any]] = []
    if "ListTasks" in raw:
        hits.append({"file": str(card_path), "line": 0, "snippet": '"ListTasks"'})
    note = card.get("conformanceNote", "")
    # 如果 conformanceNote 明确说没实现 ListTasks，则不算违规
    if not hits and "ListTasks" in note:
        return CheckResult(
            check_id="A2A-C4-declare-ListTasks",
            pass_=True,
            hits=[{"file": str(card_path), "line": 0, "snippet": 'note discloses ListTasks gap'}],
            suggestion="OK：conformanceNote 如实声明 ListTasks 未实现。",
            severity="info",
        )
    return CheckResult(
        check_id="A2A-C4-declare-ListTasks",
        pass_=bool(hits),
        hits=hits,
        suggestion="声明 `ListTasks` 或在 conformanceNote 中如实记录未实现。",
        severity="warn",
    )


def _a2a_check_signing_key(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C5: 是否声明 JWS `signing_key`。"""
    hits: list[dict[str, Any]] = []
    # 常见字段位置：顶层 signing_key / capabilities.signingKey / provider.signing_key
    candidates = []
    if "signing_key" in card:
        candidates.append(("signing_key", card["signing_key"]))
    caps = card.get("capabilities", {})
    if isinstance(caps, dict) and "signingKey" in caps:
        candidates.append(("capabilities.signingKey", caps["signingKey"]))
    prov = card.get("provider", {})
    if isinstance(prov, dict) and "signing_key" in prov:
        candidates.append(("provider.signing_key", prov["signing_key"]))
    for path, val in candidates:
        hits.append({"file": str(card_path), "line": 0, "snippet": f"{path}: {str(val)[:60]}"})
    return CheckResult(
        check_id="A2A-C5-declare-signing-key",
        pass_=bool(hits),
        hits=hits,
        suggestion="添加 signing_key 字段（占位符 `ES256:TODO` 或 JWK），A2A v1.0.1 要求。",
        severity="warn",
    )


def _a2a_check_multi_tenancy(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C6: 是否有 `multiTenancy` / `mtls` 字段。

    通过条件：至少声明一个（或明确不声明也不在 conformanceNote 谎称）。
    未声明不视为 fail，只是 warn。
    """
    hits: list[dict[str, Any]] = []
    for k in ("multiTenancy", "multi_tenancy", "mtls", "mTLS"):
        if k in card:
            hits.append({"file": str(card_path), "line": 0, "snippet": f"{k}: {card[k]}"})
    return CheckResult(
        check_id="A2A-C6-multi-tenancy-mtls",
        pass_=True,  # 通过性由是否声明决定，但即使未声明也不 fail
        hits=hits,
        suggestion="可选：声明 multiTenancy / mtls 字段以匹配 A2A v1.0.1 新特性。",
        severity="info",
    )


def _a2a_check_conformance_honest(card: dict[str, Any], card_path: Path) -> CheckResult:
    """A2A-C7: conformanceNote 必须如实（不谎称实现了未实现的能力）。

    通过条件：conformanceNote 存在且：
    - 若 card 未声明 SendMessage/GetTask/CancelTask/ListTasks 具体操作，
      note 必须明示「未实现」（含"未实现" / "NOT implemented" / "not implemented"）。
    """
    note = card.get("conformanceNote", "")
    if not note:
        return CheckResult(
            check_id="A2A-C7-conformance-honest",
            pass_=False,
            hits=[{"file": str(card_path), "line": 0, "snippet": "conformanceNote missing"}],
            suggestion="必须提供 conformanceNote 声明能力边界。",
        )
    raw = json.dumps(card, ensure_ascii=False)
    # 是否声称实现了 Send* / Get* / Cancel* / ListTasks
    claims_implemented = []
    for kw in ("SendMessage", "GetTask", "CancelTask", "ListTasks"):
        # 从 skills / extensions / capabilities 里搜
        if kw in raw and "未实现" not in note and "not implemented" not in note.lower() \
                and "NOT implemented" not in note:
            # 简单策略：如果 card 里出现 kw 且 note 未如实声明未实现，标记可疑
            claims_implemented.append(kw)
    # 判定：如果 note 明确说未实现，则 pass；如果 note 里出现 SendMessage 且含「未实现」→ pass
    note_l = note.lower()
    discloses_gap = ("未实现" in note) or ("not implemented" in note_l) or ("NOT implemented" in note)
    if discloses_gap:
        return CheckResult(
            check_id="A2A-C7-conformance-honest",
            pass_=True,
            hits=[{"file": str(card_path), "line": 0, "snippet": f"discloses gap: {note[:80]}..."}],
            suggestion="OK：conformanceNote 如实声明。",
            severity="info",
        )
    # 未声明未实现：如果 card 里出现 kw（可能是谎称），fail
    if claims_implemented:
        return CheckResult(
            check_id="A2A-C7-conformance-honest",
            pass_=False,
            hits=[{"file": str(card_path), "line": 0, "snippet": f"claims: {claims_implemented}"}],
            suggestion="conformanceNote 未如实声明 A2A 任务生命周期未实现。",
        )
    # note 存在但未提及任何未实现，也未在 card 中声称能力——通过
    return CheckResult(
        check_id="A2A-C7-conformance-honest",
        pass_=True,
        hits=[{"file": str(card_path), "line": 0, "snippet": f"note present: {note[:80]}..."}],
        suggestion="OK：conformanceNote 存在且无虚假声明。",
        severity="info",
    )


def audit_a2a(card_path: str | Path | None = None) -> A2AAuditReport:
    """对 agent-card.json 做全量审计。

    Args:
        card_path: agent-card.json 路径（默认 REPO_ROOT/agent-card.json）

    Returns:
        A2AAuditReport，含 7 项 check 结果。
    """
    p = Path(card_path) if card_path else DEFAULT_CARD_PATH
    if not p.is_file():
        return A2AAuditReport(
            card_path=str(p),
            checks=[CheckResult(
                check_id="A2A-FILE-MISSING",
                pass_=False,
                hits=[],
                suggestion=f"文件不存在: {p}",
            )],
            summary={"error": "file-missing"},
        )

    try:
        card = json.loads(_file_source(p))
    except json.JSONDecodeError as exc:
        return A2AAuditReport(
            card_path=str(p),
            checks=[CheckResult(
                check_id="A2A-FILE-INVALID-JSON",
                pass_=False,
                hits=[{"file": str(p), "line": 0, "snippet": str(exc)}],
                suggestion="agent-card.json 不是合法 JSON。",
            )],
            summary={"error": "invalid-json"},
        )

    checks = [
        _a2a_check_version(card, p),
        _a2a_check_enum_case(card, p),
        _a2a_check_send_message(card, p),
        _a2a_check_list_tasks(card, p),
        _a2a_check_signing_key(card, p),
        _a2a_check_multi_tenancy(card, p),
        _a2a_check_conformance_honest(card, p),
    ]
    report = A2AAuditReport(card_path=str(p), checks=checks)
    report.summary["protocol_target"] = "A2A v1.0.1"
    return report


# ─────────────────────────── 全量审计 ───────────────────────────

def run_full_audit(
    mcp_module_path: str | Path | None = None,
    a2a_card_path: str | Path | None = None,
) -> dict[str, Any]:
    """一次跑完 MCP + A2A 全部审计，供 CI 消费。

    Args:
        mcp_module_path: MCP server 路径
        a2a_card_path: agent-card 路径

    Returns:
        {
            "generated_at": ISO 时间戳,
            "repo_root": str,
            "mcp": <McpAuditReport.to_dict()>,
            "a2a": <A2AAuditReport.to_dict()>,
            "overall": {
                "total_checks": N,
                "passed": N,
                "failed": N,
                "all_passed": bool,
                "blocking_failures": [check_id, ...]  # 只列 severity=error 的 fail
            }
        }
    """
    from datetime import datetime, timezone

    mcp = audit_mcp(mcp_module_path)
    a2a = audit_a2a(a2a_card_path)

    all_checks = mcp.checks + a2a.checks
    total = len(all_checks)
    passed = sum(1 for c in all_checks if c.pass_)
    failed = total - passed
    blocking = [c.check_id for c in all_checks if not c.pass_ and c.severity == "error"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_root": str(REPO_ROOT),
        "mcp": mcp.to_dict(),
        "a2a": a2a.to_dict(),
        "overall": {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "all_passed": passed == total,
            "blocking_failures": blocking,
        },
    }


__all__ = [
    "CheckResult",
    "McpAuditReport",
    "A2AAuditReport",
    "audit_mcp",
    "audit_a2a",
    "run_full_audit",
    "REPO_ROOT",
    "DEFAULT_MCP_PATH",
    "DEFAULT_CARD_PATH",
    "DEFAULT_PYPROJECT_PATH",
]
