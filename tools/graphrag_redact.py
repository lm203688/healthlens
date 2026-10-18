"""图谱脱敏 CLI —— 抽取攻击防御辅助工具。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4 与 §6
         「GraphRAG 图谱 1661 节点即将公开需防抽取攻击」。

用法示例：
    # 移除所有 bibliographic 引用（作者、出版年、期刊、DOI、出版社）
    python tools/graphrag_redact.py \
        --input data/graphrag/knowledge_graph.json \
        --output data/graphrag/knowledge_graph.redacted.json \
        --report data/graphrag/redaction_report.json \
        --strip-bibliographic

    # 节点 label 哈希化（保留图结构）
    python tools/graphrag_redact.py ... --mask-node-names

    # 边属性哈希化
    python tools/graphrag_redact.py ... --hash-edges

    # 移除私有 URL
    python tools/graphrag_redact.py ... --strip-private-urls

输出：脱敏后图谱 JSON + 脱敏报告 JSON（含节点/边/字段移除计数）。
不引入新第三方依赖。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Bibliographic 字段清单
# ---------------------------------------------------------------------------

BIBLIOGRAPHIC_FIELD_NAMES: frozenset[str] = frozenset({
    "author", "authors",
    "journal", "publisher", "publisher_name",
    "year", "pubyear", "published_year", "publication_year",
    "doi", "isbn", "issn",
    "copyright", "license",
    "citation", "citations",
    "book", "book_title",
})

# 私有 URL 特征（内网/私有域名、Git remote）
PRIVATE_URL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)\b"),
    re.compile(r"(?i)^https?://[\w-]+\.(internal|corp|local|lan|private|intranet)\b"),
    re.compile(r"(?i)^(git@|ssh://|file://)"),
    re.compile(r"(?i)^https?://10\."),
    re.compile(r"(?i)^https?://192\.168\."),
    re.compile(r"(?i)^https?://172\.(1[6-9]|2\d|3[01])\."),
)


# ---------------------------------------------------------------------------
# 核心操作
# ---------------------------------------------------------------------------

def _hash_value(value: str, *, prefix: str = "", digest_len: int = 12) -> str:
    """对字符串做稳定哈希，返回 'prefix-<hex>'。"""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:digest_len]
    return f"{prefix}-{digest}" if prefix else digest


def _is_private_url(value: str) -> bool:
    return any(p.match(value) for p in PRIVATE_URL_PATTERNS)


def _strip_bibliographic_fields(props: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """移除 bibliographic 字段，返回 (new_props, removed_count)。"""
    new_props: dict[str, Any] = {}
    removed = 0
    for k, v in props.items():
        if str(k).lower() in BIBLIOGRAPHIC_FIELD_NAMES:
            removed += 1
            continue
        # 也检查值是否含 DOI 前缀
        if isinstance(v, str) and re.search(r"\b10\.\d{4,9}/", v):
            removed += 1
            continue
        new_props[k] = v
    return new_props, removed


def _hash_edge_props(edge: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """把边的 properties hash 化，保留 key。返回 (new_edge, count)。"""
    new_edge = dict(edge)
    count = 0
    if "properties" in new_edge and isinstance(new_edge["properties"], dict):
        new_props: dict[str, Any] = {}
        for k, v in new_edge["properties"].items():
            if isinstance(v, str):
                new_props[k] = _hash_value(v, prefix="hash", digest_len=12)
                count += 1
            elif isinstance(v, list):
                lst = []
                for x in v:
                    if isinstance(x, str):
                        lst.append(_hash_value(x, prefix="hash", digest_len=12))
                        count += 1
                    else:
                        lst.append(x)
                new_props[k] = lst
            else:
                new_props[k] = v
        new_edge["properties"] = new_props
    return new_edge, count


def _strip_private_urls_in_props(props: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """从节点/边 properties 中移除私有 URL 字段。返回 (new_props, removed)。"""
    new_props: dict[str, Any] = {}
    removed = 0
    for k, v in props.items():
        if isinstance(v, str) and _is_private_url(v):
            removed += 1
            continue
        if isinstance(v, list):
            new_list = []
            for x in v:
                if isinstance(x, str) and _is_private_url(x):
                    removed += 1
                    continue
                new_list.append(x)
            new_props[k] = new_list
            continue
        new_props[k] = v
    return new_props, removed


def _mask_node_label(node: dict[str, Any]) -> dict[str, Any]:
    """把节点 label hash 化，id 保留以便边关联。"""
    new_node = dict(node)
    old_label = node.get("label", "")
    if isinstance(old_label, str) and old_label:
        new_node["label"] = _hash_value(old_label, prefix="node", digest_len=12)
    return new_node


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def redact_graph(
    graph: dict[str, Any],
    *,
    strip_bibliographic: bool = False,
    mask_node_names: bool = False,
    hash_edges: bool = False,
    strip_private_urls: bool = False,
) -> tuple[dict[str, Any], dict[str, int]]:
    """对图谱做脱敏，返回 (redacted_graph, report_counts)。

    Args:
        graph: 原始图谱 dict（含 nodes/edges/meta）。
        strip_bibliographic: 移除 bibliographic 字段。
        mask_node_names: 把节点 label hash 化。
        hash_edges: 把边属性 hash 化。
        strip_private_urls: 移除私有 URL 字段。

    Returns:
        (脱敏后图谱 dict, 计数 dict)
    """
    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    meta = dict(graph.get("meta", {}) or {})

    counts = {
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "nodes_removed": 0,
        "edges_removed": 0,
        "fields_removed": 0,
        "node_labels_hashed": 0,
        "edge_props_hashed": 0,
        "private_urls_stripped": 0,
    }

    new_nodes: list[dict[str, Any]] = []
    for node in nodes:
        new_node = dict(node)
        if "properties" in new_node and isinstance(new_node["properties"], dict):
            if strip_bibliographic:
                new_node["properties"], r = _strip_bibliographic_fields(
                    new_node["properties"]
                )
                counts["fields_removed"] += r
            if strip_private_urls:
                new_node["properties"], r2 = _strip_private_urls_in_props(
                    new_node["properties"]
                )
                counts["private_urls_stripped"] += r2
                counts["fields_removed"] += r2
        if mask_node_names:
            old_label = new_node.get("label", "")
            new_node = _mask_node_label(new_node)
            if new_node.get("label") != old_label:
                counts["node_labels_hashed"] += 1
        new_nodes.append(new_node)

    new_edges: list[dict[str, Any]] = []
    for edge in edges:
        new_edge = dict(edge)
        if hash_edges:
            new_edge, cnt = _hash_edge_props(new_edge)
            counts["edge_props_hashed"] += cnt
        if strip_private_urls and isinstance(new_edge.get("properties"), dict):
            new_edge["properties"], r = _strip_private_urls_in_props(new_edge["properties"])
            counts["private_urls_stripped"] += r
            counts["fields_removed"] += r
        new_edges.append(new_edge)

    redacted = {
        "nodes": new_nodes,
        "edges": new_edges,
        "meta": {
            **meta,
            "redaction": {
                "applied_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(timespec="seconds"),
                "flags": {
                    "strip_bibliographic": strip_bibliographic,
                    "mask_node_names": mask_node_names,
                    "hash_edges": hash_edges,
                    "strip_private_urls": strip_private_urls,
                },
            },
        },
    }
    return redacted, counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="GraphRAG redact CLI —— 图谱脱敏工具"
    )
    ap.add_argument(
        "--input", "-i", required=True,
        help="输入图谱 JSON 路径",
    )
    ap.add_argument(
        "--output", "-o", required=True,
        help="输出脱敏后图谱 JSON 路径",
    )
    ap.add_argument(
        "--report", "-r",
        help="输出脱敏报告 JSON 路径（可选）",
    )
    ap.add_argument(
        "--strip-bibliographic", action="store_true",
        help="移除 author/journal/doi/year/publisher 等 bibliographic 字段",
    )
    ap.add_argument(
        "--mask-node-names", action="store_true",
        help="把节点 label 哈希化（保留 id）",
    )
    ap.add_argument(
        "--hash-edges", action="store_true",
        help="把边的 properties 值哈希化",
    )
    ap.add_argument(
        "--strip-private-urls", action="store_true",
        help="移除私有 URL 字段（内网、Git remote 等）",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)

    if not (
        args.strip_bibliographic
        or args.mask_node_names
        or args.hash_edges
        or args.strip_private_urls
    ):
        print(
            "Error: no redaction flag specified. At least one of "
            "--strip-bibliographic / --mask-node-names / --hash-edges / "
            "--strip-private-urls required.",
            file=sys.stderr,
        )
        return 2

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        graph = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {input_path}: {exc}", file=sys.stderr)
        return 1

    redacted, counts = redact_graph(
        graph,
        strip_bibliographic=args.strip_bibliographic,
        mask_node_names=args.mask_node_names,
        hash_edges=args.hash_edges,
        strip_private_urls=args.strip_private_urls,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(redacted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote redacted graph: {output_path}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "input": str(input_path),
            "output": str(output_path),
            "flags": {
                "strip_bibliographic": args.strip_bibliographic,
                "mask_node_names": args.mask_node_names,
                "hash_edges": args.hash_edges,
                "strip_private_urls": args.strip_private_urls,
            },
            **counts,
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote redaction report: {report_path}")
        print(
            f"  nodes={counts['nodes_total']} edges={counts['edges_total']} "
            f"fields_removed={counts['fields_removed']} "
            f"labels_hashed={counts['node_labels_hashed']} "
            f"edge_props_hashed={counts['edge_props_hashed']} "
            f"private_urls_stripped={counts['private_urls_stripped']}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
