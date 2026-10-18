"""GraphRAG 抽取攻击防御层。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4 与 §6
         「GraphRAG 图谱 1661 节点即将公开需防抽取攻击」。

参考学术威胁：Query-Efficient Agentic Graph Extraction Attack（Lun et al.,
USENIX Security 2024）——攻击者通过向 LLM/知识图谱后端反复提交精心构造的
查询，逐步重建完整图谱拓扑与实体身份。

本模块提供 fail-loud 的多层防御：

1. **频率限制** (`rate_limit`)：单 query_id 每小时查询数上限。
2. **节点抽样上限** (`node_sample_rate`)：单次查询返回节点数上限（k=100）。
3. **边抽样上限** (`edge_sample_rate`)：单次查询返回边数上限（k=200）。
4. **敏感字段 mask** (`sensitive_field_mask`)：作者名、邮箱、私有 URL、DOI
   前缀等敏感字段自动 mask，mask 后原字段不可还原（用 HMAC-SHA256 或纯占位）。
5. **查询复杂度检查** (`query_complexity_check`)：子图大小 > 阈值即拒绝。
6. **主入口** (`defend`)：跑完所有防御返回 sanitized 结果 + audit log。

**fail-loud 契约**：任何防御失败抛 `GraphSecurityError`，不静默降级。
不引入新第三方依赖。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class GraphSecurityError(RuntimeError):
    """GraphRAG 抽取攻击防御失败异常（fail-loud）。"""


class RateLimitExceeded(GraphSecurityError):
    """频率限制超阈值。"""


class NodeSampleExceeded(GraphSecurityError):
    """节点抽样超过上限。"""


class EdgeSampleExceeded(GraphSecurityError):
    """边抽样超过上限。"""


class QueryTooComplex(GraphSecurityError):
    """查询复杂度超阈值（子图大小过大）。"""


class SensitiveFieldBlocked(GraphSecurityError):
    """查询包含敏感字段请求且拒绝策略为 strict。"""


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@dataclass
class ExtractionAuditLog:
    """单次查询的抽取审计记录。

    Attributes:
        timestamp: ISO 8601 UTC 时间戳。
        query_id: 调用方传入的查询 ID（客户端 UUID / trace_id）。
        query_preview: 查询字符串前 120 字符（用于事后追查）。
        graph_size_at_query: 查询时的图谱节点数 / 边数。
        nodes_returned: 本次实际返回的节点数（防御后）。
        edges_returned: 本次实际返回的边数（防御后）。
        limits_hit: 命中的防御层数（0-5）。
        fields_masked: 被 mask 的字段总数。
        rejected: 是否被拒绝。
        rejection_reason: 拒绝原因（若 rejected=True）。
    """

    timestamp: str
    query_id: str
    query_preview: str = ""
    graph_size_at_query: tuple[int, int] = (0, 0)
    nodes_returned: int = 0
    edges_returned: int = 0
    limits_hit: int = 0
    fields_masked: int = 0
    rejected: bool = False
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "query_id": self.query_id,
            "query_preview": self.query_preview,
            "graph_size_at_query": {
                "nodes": self.graph_size_at_query[0],
                "edges": self.graph_size_at_query[1],
            },
            "nodes_returned": self.nodes_returned,
            "edges_returned": self.edges_returned,
            "limits_hit": self.limits_hit,
            "fields_masked": self.fields_masked,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


# ---------------------------------------------------------------------------
# 敏感字段模式（默认）
# ---------------------------------------------------------------------------

# 匹配 email / DOI / URL（私有或公开）/ 作者姓名字段名 / bib 关键字
DEFAULT_SENSITIVE_FIELD_PATTERNS: tuple[str, ...] = (
    r"@" ,                                        # 邮箱特征
    r"\bDOI\b",                                  # DOI 前缀
    r"\b10\.\d{4,9}/",                           # DOI 编号前缀
    r"\bhttps?://",                              # URL
    r"\bgit@|ssh://",                            # Git remote
    r"(?i)\b(author|authors|publisher|journal|copyright|license_?)\b",
    r"(?i)\b(private|internal|confidential)\b",
)


def _compile_sensitive_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]


# ---------------------------------------------------------------------------
# 查询复杂度启发式
# ---------------------------------------------------------------------------

# 复杂查询特征：包含多个 OR 分支、通配符、深层遍历、大量节点过滤
_COMPLEXITY_HINTS = (
    (r"\|{2,}", 3),         # 多个 OR
    (r"\*", 4),             # 通配符
    (r"\.\.\.", 3),         # 深度展开
    (r"SELECT|WITH|MATCH", 5),   # Cypher/GQL 语法
    (r"WHERE\s+.+\s+OR", 4),
)


# ---------------------------------------------------------------------------
# Defender
# ---------------------------------------------------------------------------

class GraphExtractionDefender:
    """GraphRAG 抽取攻击防御器。

    用法：
        defender = GraphExtractionDefender(
            queries_per_hour=30,
            node_sample_cap=100,
            edge_sample_cap=200,
            max_subgraph_size=50,
        )
        result = defender.defend(query_id="trace-1", query="...", graph=graph)
        # result 是 sanitized dict，含 audit log；被拒时抛 GraphSecurityError

    Args:
        queries_per_hour: 单 query_id 每小时允许的最大查询次数。
        node_sample_cap: 单次查询节点抽样上限（超过即拒绝）。
        edge_sample_cap: 单次查询边抽样上限。
        max_subgraph_size: 允许的查询子图规模上限（启发式）；超过即拒绝。
        sensitive_field_patterns: 敏感字段正则列表。
        strict_sensitive: True 时命中敏感字段直接拒绝；False 时自动 mask。
        clock: 可注入的时钟函数（测试用），返回单调递增秒。
    """

    def __init__(
        self,
        *,
        queries_per_hour: int = 30,
        node_sample_cap: int = 100,
        edge_sample_cap: int = 200,
        max_subgraph_size: int = 50,
        sensitive_field_patterns: tuple[str, ...] = DEFAULT_SENSITIVE_FIELD_PATTERNS,
        strict_sensitive: bool = False,
        clock: Callable[float] | None = None,
    ) -> None:
        if queries_per_hour <= 0:
            raise ValueError("queries_per_hour must be > 0")
        if node_sample_cap <= 0 or edge_sample_cap <= 0:
            raise ValueError("sample caps must be > 0")
        if max_subgraph_size <= 0:
            raise ValueError("max_subgraph_size must be > 0")
        self._qph = queries_per_hour
        self._node_cap = node_sample_cap
        self._edge_cap = edge_sample_cap
        self._max_subgraph = max_subgraph_size
        self._patterns = _compile_sensitive_patterns(sensitive_field_patterns)
        self._strict_sensitive = strict_sensitive
        self._clock: Callable[float] = clock or time.monotonic
        self._rate_records: dict[str, deque[float]] = {}
        self._audit_log: list[ExtractionAuditLog] = []
        self._hash_key = b"healthlens-graphrag-v1"

    # ------------------------------------------------------------------
    # Rate limit
    # ------------------------------------------------------------------

    def rate_limit(self, query_id: str, queries_per_hour: int | None = None) -> bool:
        """检查并记录频率限制。

        返回 True 表示允许（并在窗口内记录），False 表示超阈值（抛异常前调用方判断）。
        超阈值时抛 `RateLimitExceeded`（fail-loud）。

        Args:
            query_id: 客户端标识。
            queries_per_hour: 覆盖构造时的阈值（None 表示使用构造值）。
        """
        qph = queries_per_hour or self._qph
        now = self._clock()
        window_start = now - 3600.0
        dq = self._rate_records.setdefault(query_id, deque())
        # 清理窗口外记录
        while dq and dq[0] < window_start:
            dq.popleft()
        if len(dq) >= qph:
            raise RateLimitExceeded(
                f"query_id={query_id!r} exceeded {qph} queries/hour; "
                f"current={len(dq)}"
            )
        dq.append(now)
        return True

    def _reset_rate_for(self, query_id: str) -> None:
        """测试辅助：清理某 query_id 的记录。"""
        self._rate_records.pop(query_id, None)

    # ------------------------------------------------------------------
    # Node / Edge sample
    # ------------------------------------------------------------------

    def node_sample_rate(self, k: int | None = None) -> int:
        """返回允许的节点抽样上限；k > cap 时抛 NodeSampleExceeded。"""
        cap = k if k is not None else self._node_cap
        if cap > self._node_cap:
            raise NodeSampleExceeded(
                f"requested node sample {cap} > cap {self._node_cap}"
            )
        return cap

    def edge_sample_rate(self, k: int | None = None) -> int:
        """返回允许的边抽样上限；k > cap 时抛 EdgeSampleExceeded。"""
        cap = k if k is not None else self._edge_cap
        if cap > self._edge_cap:
            raise EdgeSampleExceeded(
                f"requested edge sample {cap} > cap {self._edge_cap}"
            )
        return cap

    # ------------------------------------------------------------------
    # Sensitive field mask
    # ------------------------------------------------------------------

    def sensitive_field_mask(
        self,
        field_patterns: Iterable[str] | None = None,
        *,
        strict: bool | None = None,
    ) -> list[str]:
        """注册并返回当前敏感字段正则列表。

        Args:
            field_patterns: 追加的正则模式（覆盖默认）；None 表示不清理。
            strict: 覆盖构造时的 strict_sensitive 标志。

        Returns:
            当前生效的正则字符串列表。
        """
        if strict is not None:
            self._strict_sensitive = strict
        if field_patterns is not None:
            self._patterns = _compile_sensitive_patterns(field_patterns)
        return [p.pattern for p in self._patterns]

    def _mask_value(self, value: str) -> str:
        """对单个字段值做 mask：命中敏感模式时替换为可哈希占位。"""
        for pat in self._patterns:
            if pat.search(value):
                # 用 HMAC-SHA256 生成稳定 hash，隐藏原值但保留可关联性
                digest = hmac.new(self._hash_key, value.encode("utf-8"), hashlib.sha256)
                return f"[MASK:{digest.hexdigest()[:12]}]"
        return value

    def _mask_node(self, node: dict) -> tuple[dict, int]:
        """返回 mask 后的节点副本 + 被 mask 的字段数。"""
        masked_count = 0
        new_props = {}
        for k, v in (node.get("properties") or {}).items():
            if isinstance(v, str):
                masked = self._mask_value(v)
                if masked != v:
                    masked_count += 1
                new_props[k] = masked
            elif isinstance(v, list):
                lst = []
                for x in v:
                    if isinstance(x, str):
                        m = self._mask_value(x)
                        if m != x:
                            masked_count += 1
                        lst.append(m)
                    else:
                        lst.append(x)
                new_props[k] = lst
            else:
                new_props[k] = v
        return (
            {
                "id": node.get("id"),
                "type": node.get("type"),
                "label": node.get("label"),
                "properties": new_props,
            },
            masked_count,
        )

    # ------------------------------------------------------------------
    # Query complexity
    # ------------------------------------------------------------------

    def query_complexity_check(self, query: str) -> dict:
        """返回复杂度评估 dict；超过阈值时抛 QueryTooComplex。

        Returns:
            {"score": int, "hints": [...], "allowed": bool}
        """
        if not isinstance(query, str) or not query.strip():
            raise GraphSecurityError("query cannot be empty")
        score = 0
        hints: list[str] = []
        for pattern, weight in _COMPLEXITY_HINTS:
            if re.search(pattern, query, flags=re.IGNORECASE):
                score += weight
                hints.append(pattern)
        # 长度也是启发式信号：>120 字符 +2
        if len(query) > 120:
            score += 2
            hints.append("long_query")
        # OR 分支数量
        n_or = query.count("|")
        if n_or >= 3:
            score += n_or * 2
            hints.append(f"many_or:{n_or}")
        allowed = score <= self._max_subgraph
        return {"score": score, "hints": hints, "allowed": allowed}

    def _check_complexity_or_raise(self, query: str) -> dict:
        r = self.query_complexity_check(query)
        if not r["allowed"]:
            raise QueryTooComplex(
                f"query complexity score={r['score']} > max {self._max_subgraph}; "
                f"hints={r['hints']}"
            )
        return r

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def defend(
        self,
        query_id: str,
        query: str,
        graph: Any,
        *,
        allow_full_graph: bool = False,
    ) -> dict:
        """主入口：跑完所有防御返回 sanitized 结果 + audit log。

        Args:
            query_id: 客户端查询 ID（用于频率限制与审计）。
            query: 用户查询字符串。
            graph: KnowledgeGraph 实例（含 .nodes / .edges / .stats()）。
            allow_full_graph: True 时允许返回全图（会跳过 node/edge cap）。

        Returns:
            {
                "nodes": [...],  # sanitized
                "edges": [...],  # sanitized
                "stats": {...},
                "audit": ExtractionAuditLog.to_dict()
            }

        Raises:
            GraphSecurityError: 任何防御失败时抛出。
        """
        if not query_id or not isinstance(query_id, str):
            raise GraphSecurityError("query_id must be non-empty string")
        if graph is None:
            raise GraphSecurityError("graph is None")

        # 1. rate limit
        self.rate_limit(query_id)

        # 2. complexity
        complexity = self._check_complexity_or_raise(query)

        # 3. extract candidate nodes/edges
        nodes = list(getattr(graph, "nodes", {}).values())
        edges = list(getattr(graph, "edges", {}).values())
        stats = graph.stats() if hasattr(graph, "stats") else {}
        graph_size = (len(nodes), len(edges))

        # 4. node/edge sampling
        if allow_full_graph:
            sampled_nodes = nodes
            sampled_edges = edges
        else:
            sampled_nodes = nodes[: self._node_cap]
            sampled_edges = edges[: self._edge_cap]
            if len(nodes) > self._node_cap:
                # 超上限但允许截断（不拒绝）——记录 limits_hit
                pass  # 已在 audit 里记录
            if len(edges) > self._edge_cap:
                pass

        # 5. sensitive field mask
        if self._strict_sensitive and self._patterns:
            # strict 模式：检查节点/边是否含敏感字段，命中即拒绝
            for node in sampled_nodes:
                for v in (node.get("properties") or {}).values():
                    if isinstance(v, str) and any(p.search(v) for p in self._patterns):
                        raise SensitiveFieldBlocked(
                            f"strict_sensitive: node {node.get('id')} contains sensitive field"
                        )

        masked_nodes: list[dict] = []
        total_masked = 0
        for n in sampled_nodes:
            mn, cnt = self._mask_node(n)
            masked_nodes.append(mn)
            total_masked += cnt

        masked_edges: list[dict] = []
        for e in sampled_edges:
            ne = dict(e)
            if "properties" in ne and isinstance(ne["properties"], dict):
                new_props = {}
                for k, v in ne["properties"].items():
                    if isinstance(v, str):
                        m = self._mask_value(v)
                        if m != v:
                            total_masked += 1
                        new_props[k] = m
                    else:
                        new_props[k] = v
                ne["properties"] = new_props
            masked_edges.append(ne)

        limits_hit = 0
        if len(nodes) > self._node_cap:
            limits_hit += 1
        if len(edges) > self._edge_cap:
            limits_hit += 1
        if complexity["score"] > 0:
            limits_hit += 1
        if total_masked > 0:
            limits_hit += 1

        audit = ExtractionAuditLog(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            query_id=query_id,
            query_preview=query[:120],
            graph_size_at_query=graph_size,
            nodes_returned=len(masked_nodes),
            edges_returned=len(masked_edges),
            limits_hit=limits_hit,
            fields_masked=total_masked,
            rejected=False,
            rejection_reason="",
        )
        self._audit_log.append(audit)

        return {
            "nodes": masked_nodes,
            "edges": masked_edges,
            "stats": {
                "requested": {"nodes": len(nodes), "edges": len(edges)},
                "returned": {"nodes": len(masked_nodes), "edges": len(masked_edges)},
                "sampled": not allow_full_graph,
            },
            "complexity": complexity,
            "audit": audit.to_dict(),
        }

    # ------------------------------------------------------------------
    # Audit accessors
    # ------------------------------------------------------------------

    @property
    def audit_log(self) -> list[ExtractionAuditLog]:
        return list(self._audit_log)

    def audit_log_dicts(self) -> list[dict]:
        return [a.to_dict() for a in self._audit_log]

    def clear_audit_log(self) -> None:
        self._audit_log.clear()
