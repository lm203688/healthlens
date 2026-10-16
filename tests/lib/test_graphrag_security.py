"""GraphRAG 抽取攻击防御测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4 与 §6
         「GraphRAG 图谱 1661 节点即将公开需防抽取攻击」。

覆盖：
- rate_limit：超阈值拒绝、单用户 vs 多用户
- node_sample_rate：全图被拒、子图允许、边缘节点被优先保留（cap 生效）
- edge_sample_rate：同上
- sensitive_field_mask：各种字段模式匹配、mask 后原字段不可还原
- query_complexity_check：简单查询通过、复杂查询拒绝
- defend 主流程：正常查询、被拒查询、部分命中限制
- audit log：字段完整性、时序正确
- redact CLI：strip-bibliographic 完整移除、mask-node-names hash 化后可反查
  （通过 hash 前缀对齐）
"""
from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.lib.graphrag_security import (
    EdgeSampleExceeded,
    ExtractionAuditLog,
    GraphExtractionDefender,
    GraphSecurityError,
    NodeSampleExceeded,
    QueryTooComplex,
    RateLimitExceeded,
    SensitiveFieldBlocked,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPHRAG_REDACT_CLI = REPO_ROOT / "tools" / "graphrag_redact.py"
KNOWLEDGE_GRAPH_JSON = REPO_ROOT / "data" / "graphrag" / "knowledge_graph.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeGraph:
    """最小伪造 KnowledgeGraph：满足 defender.defend 的需求。"""

    def __init__(self, nodes: list[dict], edges: list[dict]) -> None:
        self._nodes = {n["id"]: n for n in nodes}
        self._edges = {
            f"{e['src']}||{e['dst']}||{e['relation']}": e
            for e in edges
        }

    @property
    def nodes(self) -> dict:
        return dict(self._nodes)

    @property
    def edges(self) -> dict:
        return dict(self._edges)

    def stats(self) -> dict:
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
        }


@pytest.fixture
def small_graph() -> _FakeGraph:
    nodes = [
        {"id": "n1", "type": "herb", "label": "黄芪", "properties": {"source": "sne"}},
        {"id": "n2", "type": "herb", "label": "当归", "properties": {}},
        {"id": "n3", "type": "condition", "label": "气虚", "properties": {}},
        {"id": "n4", "type": "axis", "label": "气化轴", "properties": {"axis_id": "A"}},
    ]
    edges = [
        {"src": "n1", "dst": "n3", "relation": "treats", "properties": {}},
        {"src": "n2", "dst": "n3", "relation": "treats", "properties": {}},
        {"src": "n1", "dst": "n4", "relation": "axis_of", "properties": {"axis_id": "A"}},
    ]
    return _FakeGraph(nodes, edges)


@pytest.fixture
def large_graph() -> _FakeGraph:
    """120 节点 / 300 边——超过默认 cap (100/200)。

    用双循环遍历所有 (src,dst) 组合直到凑够 300 条唯一边，
    避免单一 mod 表达式导致的去重后不足问题。
    """
    nodes = [
        {"id": f"n{i}", "type": "herb", "label": f"h{i}", "properties": {}}
        for i in range(120)
    ]
    seen: set[str] = set()
    unique_edges: list[dict] = []
    src_i = 0
    dst_offset = 1
    while len(unique_edges) < 300 and src_i < 120:
        dst_i = (src_i + dst_offset) % 120
        while len(unique_edges) < 300 and dst_i != src_i:
            src = f"n{src_i}"
            dst = f"n{dst_i}"
            key = f"{src}||{dst}||treats"
            if key not in seen:
                seen.add(key)
                unique_edges.append({"src": src, "dst": dst, "relation": "treats",
                                     "properties": {}})
            dst_i = (dst_i + 1) % 120
        src_i += 1
    assert len(unique_edges) >= 300, f"only generated {len(unique_edges)} unique edges"
    return _FakeGraph(nodes, unique_edges[:300])


@pytest.fixture
def monotonic_clock() -> list[float]:
    """可注入的单调递增时钟状态容器。"""
    return [1_000_000.0]


def make_clock(state: list[float]):
    """返回一个可注入的单调递增时钟闭包。"""
    def _clock() -> float:
        state[0] += 1.0
        return state[0]
    return _clock


# ---------------------------------------------------------------------------
# 1. Rate limit
# ---------------------------------------------------------------------------

class TestRateLimit:
    """频率限制。"""

    def test_within_limit_allows(self, monotonic_clock):
        d = GraphExtractionDefender(queries_per_hour=5, clock=make_clock(monotonic_clock))
        for _ in range(5):
            assert d.rate_limit("u1") is True

    def test_over_limit_raises(self, monotonic_clock):
        d = GraphExtractionDefender(queries_per_hour=3, clock=make_clock(monotonic_clock))
        for _ in range(3):
            d.rate_limit("u1")
        with pytest.raises(RateLimitExceeded):
            d.rate_limit("u1")

    def test_multi_user_independent(self, monotonic_clock):
        d = GraphExtractionDefender(queries_per_hour=2, clock=make_clock(monotonic_clock))
        for _ in range(2):
            d.rate_limit("u1")
        # u1 应被拒，u2 应允许
        with pytest.raises(RateLimitExceeded):
            d.rate_limit("u1")
        assert d.rate_limit("u2") is True

    def test_rate_limit_per_call_override(self, monotonic_clock):
        d = GraphExtractionDefender(queries_per_hour=10, clock=make_clock(monotonic_clock))
        for _ in range(3):
            d.rate_limit("u1", queries_per_hour=3)
        with pytest.raises(RateLimitExceeded):
            d.rate_limit("u1", queries_per_hour=3)


# ---------------------------------------------------------------------------
# 2. Node / Edge sample rate
# ---------------------------------------------------------------------------

class TestSampleCaps:
    """节点/边抽样上限。"""

    def test_node_sample_within_cap_ok(self):
        d = GraphExtractionDefender(node_sample_cap=100)
        assert d.node_sample_rate(50) == 50

    def test_node_sample_over_cap_raises(self):
        d = GraphExtractionDefender(node_sample_cap=100)
        with pytest.raises(NodeSampleExceeded):
            d.node_sample_rate(200)

    def test_edge_sample_within_cap_ok(self):
        d = GraphExtractionDefender(edge_sample_cap=200)
        assert d.edge_sample_rate(150) == 150

    def test_edge_sample_over_cap_raises(self):
        d = GraphExtractionDefender(edge_sample_cap=200)
        with pytest.raises(EdgeSampleExceeded):
            d.edge_sample_rate(500)

    def test_default_caps_returned(self):
        d = GraphExtractionDefender(node_sample_cap=100, edge_sample_cap=200)
        assert d.node_sample_rate() == 100
        assert d.edge_sample_rate() == 200


# ---------------------------------------------------------------------------
# 3. Sensitive field mask
# ---------------------------------------------------------------------------

class TestSensitiveFieldMask:
    """敏感字段 mask。"""

    def test_email_masked(self):
        d = GraphExtractionDefender()
        # 构造含邮箱属性的节点
        node = {"id": "n1", "type": "herb", "label": "x",
                "properties": {"contact": "alice@example.com"}}
        masked, cnt = d._mask_node(node)
        assert cnt == 1
        assert "alice@example.com" not in json.dumps(masked, ensure_ascii=False)
        assert "[MASK:" in masked["properties"]["contact"]

    def test_doi_masked(self):
        d = GraphExtractionDefender()
        node = {"id": "n1", "type": "herb", "label": "x",
                "properties": {"doi": "10.1016/S0002-9149(20)30001-1"}}
        masked, cnt = d._mask_node(node)
        assert cnt == 1
        assert "10.1016" not in json.dumps(masked, ensure_ascii=False)

    def test_url_masked(self):
        d = GraphExtractionDefender()
        node = {"id": "n1", "type": "herb", "label": "x",
                "properties": {"src": "https://private.internal/foo"}}
        masked, cnt = d._mask_node(node)
        assert cnt == 1
        assert "https://" not in masked["properties"]["src"]

    def test_clean_node_not_masked(self):
        d = GraphExtractionDefender()
        node = {"id": "n1", "type": "herb", "label": "黄芪",
                "properties": {"source": "神农本草经"}}
        masked, cnt = d._mask_node(node)
        assert cnt == 0
        assert masked["properties"]["source"] == "神农本草经"

    def test_mask_is_stable_hash(self):
        """同一字段值 mask 后应保持一致（HMAC 稳定）。"""
        d = GraphExtractionDefender()
        n1 = {"id": "n1", "type": "x", "label": "x", "properties": {"a": "alice@x.com"}}
        n2 = {"id": "n2", "type": "x", "label": "x", "properties": {"a": "alice@x.com"}}
        m1, _ = d._mask_node(n1)
        m2, _ = d._mask_node(n2)
        assert m1["properties"]["a"] == m2["properties"]["a"]

    def test_mask_not_reversible(self):
        """mask 后原字段不可通过简单比较还原（长度显著不同）。"""
        d = GraphExtractionDefender()
        node = {"id": "n1", "type": "x", "label": "x",
                "properties": {"email": "alice@example.com"}}
        masked, _ = d._mask_node(node)
        masked_val = masked["properties"]["email"]
        # 原值不应出现在 mask 结果里
        assert "alice@example.com" not in masked_val
        # mask 值应短于原值 hash 全长度（截断）
        assert len(masked_val) <= 20

    def test_sensitive_field_patterns_override(self):
        d = GraphExtractionDefender()
        pats = d.sensitive_field_mask(("@x\\.corp$",))
        assert pats == [r"@x\.corp$"]

    def test_strict_mode_rejects(self, small_graph, monkeypatch):
        # 注入一个含 email 属性的节点到内部 store
        monkeypatch.setattr(
            small_graph, "_nodes",
            {**small_graph._nodes, "n5": {
                "id": "n5", "type": "herb", "label": "x",
                "properties": {"email": "x@x.com"},
            }},
        )
        d = GraphExtractionDefender(strict_sensitive=True)
        with pytest.raises(SensitiveFieldBlocked):
            d.defend(query_id="q-strict", query="show all herbs", graph=small_graph)


# ---------------------------------------------------------------------------
# 4. Query complexity
# ---------------------------------------------------------------------------

class TestQueryComplexity:
    """查询复杂度检查。"""

    def test_simple_query_ok(self):
        d = GraphExtractionDefender()
        r = d.query_complexity_check("show herbs for qixu")
        assert r["allowed"] is True
        assert r["score"] == 0

    def test_many_or_rejected(self):
        d = GraphExtractionDefender(max_subgraph_size=10)
        # 7 个 OR 分支（6 个 |）+ 通配符，总分 >10
        q = "a | b | c | d | e | f | g"
        r = d.query_complexity_check(q)
        assert r["score"] > 10
        with pytest.raises(QueryTooComplex):
            d._check_complexity_or_raise(q)

    def test_wildcard_increases_score(self):
        d = GraphExtractionDefender()
        r = d.query_complexity_check("node* .*")
        assert r["score"] > 0
        assert "*" in " ".join(r["hints"]) or any("*" in h for h in r["hints"])

    def test_cypher_syntax_rejected(self):
        d = GraphExtractionDefender(max_subgraph_size=5)
        # MATCH + WHERE OR + 通配符，总分 >5
        q = "MATCH (n) WHERE n.name = 'x' OR n.x OR n.y RETURN n"
        with pytest.raises(QueryTooComplex):
            d._check_complexity_or_raise(q)

    def test_empty_query_raises(self):
        d = GraphExtractionDefender()
        with pytest.raises(GraphSecurityError):
            d.query_complexity_check("")


# ---------------------------------------------------------------------------
# 5. Defend main flow
# ---------------------------------------------------------------------------

class TestDefend:
    """主入口 defend 流程。"""

    def test_normal_query_returns_nodes_edges(self, small_graph):
        d = GraphExtractionDefender()
        result = d.defend(query_id="q1", query="show herbs", graph=small_graph)
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result
        assert "audit" in result
        assert result["stats"]["returned"]["nodes"] == 4
        assert result["stats"]["returned"]["edges"] == 3

    def test_large_graph_hits_sample_limits(self, large_graph):
        d = GraphExtractionDefender(node_sample_cap=100, edge_sample_cap=200)
        result = d.defend(query_id="q-large", query="dump all", graph=large_graph)
        assert result["stats"]["requested"]["nodes"] == 120
        assert result["stats"]["returned"]["nodes"] == 100
        assert result["stats"]["requested"]["edges"] == 300
        assert result["stats"]["returned"]["edges"] == 200
        assert result["audit"]["limits_hit"] >= 2  # node + edge cap

    def test_allow_full_graph_bypasses_caps(self, large_graph):
        d = GraphExtractionDefender(node_sample_cap=50)
        result = d.defend(
            query_id="q-full", query="ok", graph=large_graph, allow_full_graph=True
        )
        assert result["stats"]["returned"]["nodes"] == 120

    def test_complex_query_rejected(self, small_graph):
        d = GraphExtractionDefender(max_subgraph_size=5)
        with pytest.raises(QueryTooComplex):
            d.defend(
                query_id="q-complex",
                query="MATCH (a)-[r]->(b)-[s]->(c) WHERE a.x OR b.x OR c.x",
                graph=small_graph,
            )

    def test_invalid_query_id_raises(self, small_graph):
        d = GraphExtractionDefender()
        with pytest.raises(GraphSecurityError):
            d.defend(query_id="", query="x", graph=small_graph)

    def test_none_graph_raises(self):
        d = GraphExtractionDefender()
        with pytest.raises(GraphSecurityError):
            d.defend(query_id="q1", query="x", graph=None)

    def test_partial_mask_records_audit(self, small_graph):
        # 注入敏感字段（nodes 属性返回副本，需改内部 _nodes）
        small_graph._nodes["n9"] = {
            "id": "n9", "type": "herb", "label": "secret",
            "properties": {"email": "x@x.com"},
        }
        d = GraphExtractionDefender(node_sample_cap=10)
        result = d.defend(query_id="q-mask", query="show herbs", graph=small_graph)
        assert result["audit"]["fields_masked"] >= 1
        # 被 mask 字段不可还原
        for n in result["nodes"]:
            assert "x@x.com" not in json.dumps(n, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 6. Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    """审计日志。"""

    def test_audit_log_populated_after_defend(self, small_graph):
        d = GraphExtractionDefender()
        d.defend(query_id="a1", query="q1", graph=small_graph)
        d.defend(query_id="a2", query="q2", graph=small_graph)
        logs = d.audit_log
        assert len(logs) == 2

    def test_audit_log_field_completeness(self, small_graph):
        d = GraphExtractionDefender()
        d.defend(query_id="a1", query="q1", graph=small_graph)
        a = d.audit_log[0]
        # dataclass 所有字段齐全
        for fld in (
            "timestamp", "query_id", "query_preview", "graph_size_at_query",
            "nodes_returned", "edges_returned", "limits_hit", "fields_masked",
            "rejected", "rejection_reason",
        ):
            assert hasattr(a, fld)
        d_dict = a.to_dict()
        assert d_dict["graph_size_at_query"]["nodes"] == 4
        assert d_dict["graph_size_at_query"]["edges"] == 3
        assert d_dict["rejected"] is False

    def test_audit_log_time_order(self, small_graph, monotonic_clock):
        d = GraphExtractionDefender(clock=make_clock(monotonic_clock))
        d.defend(query_id="x", query="q", graph=small_graph)
        d.defend(query_id="x", query="q", graph=small_graph)
        d.defend(query_id="x", query="q", graph=small_graph)
        logs = d.audit_log
        # 时间戳按调用顺序递增
        times = [log.timestamp for log in logs]
        assert times == sorted(times)

    def test_audit_log_dicts_serializable(self, small_graph):
        d = GraphExtractionDefender()
        d.defend(query_id="x", query="q", graph=small_graph)
        dicts = d.audit_log_dicts()
        assert isinstance(dicts, list)
        # 可 JSON 序列化
        _ = json.dumps(dicts, ensure_ascii=False)

    def test_clear_audit_log(self, small_graph):
        d = GraphExtractionDefender()
        d.defend(query_id="x", query="q", graph=small_graph)
        d.clear_audit_log()
        assert d.audit_log == []


# ---------------------------------------------------------------------------
# 7. Construction edge cases
# ---------------------------------------------------------------------------

class TestDefenderConstruction:
    """构造与异常路径。"""

    def test_zero_qph_raises(self):
        with pytest.raises(ValueError):
            GraphExtractionDefender(queries_per_hour=0)

    def test_zero_node_cap_raises(self):
        with pytest.raises(ValueError):
            GraphExtractionDefender(node_sample_cap=0)

    def test_zero_max_subgraph_raises(self):
        with pytest.raises(ValueError):
            GraphExtractionDefender(max_subgraph_size=0)

    def test_audit_log_dataclass_to_dict_shape(self):
        a = ExtractionAuditLog(
            timestamp="2026-10-16T00:00:00+00:00",
            query_id="q1",
            query_preview="q1",
            graph_size_at_query=(100, 200),
            nodes_returned=10,
            edges_returned=20,
            limits_hit=1,
            fields_masked=0,
            rejected=True,
            rejection_reason="rate_limit",
        )
        d = a.to_dict()
        assert d["rejected"] is True
        assert d["rejection_reason"] == "rate_limit"
        assert d["graph_size_at_query"]["nodes"] == 100


# ---------------------------------------------------------------------------
# 8. Redact CLI integration
# ---------------------------------------------------------------------------

class TestRedactCLI:
    """tools/graphrag_redact.py CLI。"""

    def _run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GRAPHRAG_REDACT_CLI), *args],
            cwd=str(cwd), capture_output=True, text=True, timeout=60,
        )

    def test_cli_help(self):
        r = self._run(["--help"], REPO_ROOT)
        assert r.returncode == 0
        assert "redact" in (r.stdout + r.stderr).lower() or "strip" in (r.stdout + r.stderr).lower()

    def test_strip_bibliographic_removes_fields(self, tmp_path):
        # 构造一个包含 bibliographic 字段的小图谱
        graph = {
            "nodes": [
                {"id": "n1", "type": "herb", "label": "黄芪",
                 "properties": {
                     "author": "张仲景",
                     "journal": "神农本草经",
                     "year": 220,
                     "doi": "10.1234/sne.2000",
                     "publisher": "中医古籍出版社",
                     "source": "神农本草经",
                 }},
                {"id": "n2", "type": "herb", "label": "当归",
                 "properties": {"source": "食疗本草"}},
            ],
            "edges": [
                {"src": "n1", "dst": "n2", "relation": "relates_to",
                 "properties": {"author": "李时珍", "year": 1578}},
            ],
            "meta": {"version": "graphrag/v1"},
        }
        src = tmp_path / "kg.json"
        src.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        out_graph = tmp_path / "kg.redacted.json"
        out_report = tmp_path / "report.json"

        r = self._run([
            "--input", str(src),
            "--output", str(out_graph),
            "--report", str(out_report),
            "--strip-bibliographic",
        ], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert out_graph.is_file()
        assert out_report.is_file()

        redacted = json.loads(out_graph.read_text(encoding="utf-8"))
        # author / journal / year / doi / publisher 应被移除
        n1_props = redacted["nodes"][0]["properties"]
        for forbidden in ("author", "journal", "year", "doi", "publisher"):
            assert forbidden not in n1_props, f"{forbidden} should be stripped"
        # source 应保留
        assert "source" in n1_props

        report = json.loads(out_report.read_text(encoding="utf-8"))
        assert report["fields_removed"] >= 5  # author+journal+year+doi+publisher

    def test_mask_node_names_hashes_labels(self, tmp_path):
        graph = {
            "nodes": [
                {"id": "n1", "type": "herb", "label": "黄芪", "properties": {}},
                {"id": "n2", "type": "herb", "label": "当归", "properties": {}},
            ],
            "edges": [
                {"src": "n1", "dst": "n2", "relation": "treats", "properties": {}},
            ],
            "meta": {},
        }
        src = tmp_path / "kg.json"
        src.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "kg.redacted.json"
        out_report = tmp_path / "report.json"

        r = self._run([
            "--input", str(src), "--output", str(out),
            "--report", str(out_report),
            "--mask-node-names",
        ], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        redacted = json.loads(out.read_text(encoding="utf-8"))
        # label 应被 hash 化，原 label 不应出现
        for n in redacted["nodes"]:
            assert "黄芪" not in n["label"]
            assert "当归" not in n["label"]
            assert n["label"].startswith("node-")

        # 图结构保留：边数不变
        assert len(redacted["edges"]) == 1

        # hash 前缀对齐：hash(label) 应可预测
        n1_hash = hashlib.sha256("黄芪".encode("utf-8")).hexdigest()[:12]
        n2_hash = hashlib.sha256("当归".encode("utf-8")).hexdigest()[:12]
        labels = {n["id"]: n["label"] for n in redacted["nodes"]}
        assert labels["n1"] == f"node-{n1_hash}"
        assert labels["n2"] == f"node-{n2_hash}"

    def test_hash_edges_removes_edge_props(self, tmp_path):
        graph = {
            "nodes": [
                {"id": "n1", "type": "herb", "label": "x", "properties": {}},
                {"id": "n2", "type": "herb", "label": "y", "properties": {}},
            ],
            "edges": [
                {"src": "n1", "dst": "n2", "relation": "treats",
                 "properties": {"evidence": "secret-payload-1234"}},
            ],
            "meta": {},
        }
        src = tmp_path / "kg.json"
        src.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "kg.redacted.json"
        out_report = tmp_path / "report.json"

        r = self._run([
            "--input", str(src), "--output", str(out),
            "--report", str(out_report),
            "--hash-edges",
        ], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        redacted = json.loads(out.read_text(encoding="utf-8"))
        # 原属性值应被替换为 hash
        assert "secret-payload-1234" not in json.dumps(redacted, ensure_ascii=False)

    def test_strip_private_urls(self, tmp_path):
        graph = {
            "nodes": [
                {"id": "n1", "type": "herb", "label": "x",
                 "properties": {"url": "https://private.internal/foo"}},
                {"id": "n2", "type": "herb", "label": "y",
                 "properties": {"url": "https://public.example.com/bar"}},
            ],
            "edges": [],
            "meta": {},
        }
        src = tmp_path / "kg.json"
        src.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "kg.redacted.json"
        out_report = tmp_path / "report.json"

        r = self._run([
            "--input", str(src), "--output", str(out),
            "--report", str(out_report),
            "--strip-private-urls",
        ], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        redacted = json.loads(out.read_text(encoding="utf-8"))
        dumped = json.dumps(redacted, ensure_ascii=False)
        assert "private.internal" not in dumped
        # 私有 URL 字段应被移除或替换
        n1 = next(n for n in redacted["nodes"] if n["id"] == "n1")
        assert "url" not in n1["properties"] or "[MASK" in str(n1["properties"].get("url", ""))

    def test_combined_flags_report_counts(self, tmp_path):
        graph = {
            "nodes": [
                {"id": "n1", "type": "herb", "label": "黄芪",
                 "properties": {"author": "张仲景", "doi": "10.1/x"}},
            ],
            "edges": [
                {"src": "n1", "dst": "n1", "relation": "self",
                 "properties": {"note": "abc"}},
            ],
            "meta": {},
        }
        src = tmp_path / "kg.json"
        src.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "kg.redacted.json"
        out_report = tmp_path / "report.json"

        r = self._run([
            "--input", str(src), "--output", str(out),
            "--report", str(out_report),
            "--strip-bibliographic", "--hash-edges",
        ], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        report = json.loads(out_report.read_text(encoding="utf-8"))
        assert report["nodes_total"] == 1
        assert report["edges_total"] == 1
        # author + doi = 2 字段被移除
        assert report["fields_removed"] == 2
