"""GraphRAG 知识图谱引擎（S2-5）

纯 Python 实现的内存知识图谱：节点 + 有向边 + BFS 遍历。

设计要点：
- 不依赖 networkx / pygraph 等第三方图库；所有遍历、查询自实现。
- fail-loud：源数据全部缺失时明确抛错，不静默降级为空图。
- 缓存：load_graph() 优先读 data/graphrag/knowledge_graph.json，缺失才重建。
- wellness 边界：本引擎只做结构化查询，不做任何诊断/治疗判断。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 图谱规模上限，防止内存爆炸（源数据未来扩容时兜底）
MAX_NODES = 5000
MAX_EDGES = 50000

# 缓存文件位置
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_GRAPH_CACHE_DIR = _DATA_DIR / "graphrag"
_GRAPH_CACHE_FILE = _GRAPH_CACHE_DIR / "knowledge_graph.json"


class KnowledgeGraph:
    """纯内存知识图谱，节点 + 有向边。"""

    def __init__(self, *, meta: dict[str, Any] | None = None):
        # 节点表：id → node dict
        self.nodes: dict[str, dict] = {}
        # 边表：边 key → edge dict（edge key = "src||dst||relation"）
        self.edges: dict[str, dict] = {}
        # 反向索引（加速查询，惰性维护）
        self._out_index: dict[str, list[str]] = {}  # node_id → [edge_key]
        self._in_index: dict[str, list[str]] = {}   # node_id → [edge_key]
        # 类型索引
        self._type_index: dict[str, list[str]] = {}  # node_type → [node_id]
        self.meta: dict[str, Any] = meta or {}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_key(src: str, dst: str, relation: str) -> str:
        return f"{src}||{dst}||{relation}"

    @staticmethod
    def _node_id(node_id: str, node_type: str, label: str) -> str:
        # 优先用调用方传入的 node_id；否则按类型+label 生成
        return node_id

    # ------------------------------------------------------------------
    # 基础写入
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, node_type: str, label: str, **props: Any) -> dict:
        """新增或更新节点。返回节点 dict。"""
        if not node_id:
            raise ValueError("node_id 不能为空")
        if not node_type:
            raise ValueError("node_type 不能为空")
        if not label:
            raise ValueError("label 不能为空")
        if len(self.nodes) >= MAX_NODES:
            raise ValueError(
                f"图谱已达最大节点数 {MAX_NODES}；拒绝新增节点 {node_id}（fail-loud）"
            )
        node: dict[str, Any] = self.nodes.get(node_id) or {
            "id": node_id,
            "type": node_type,
            "label": label,
            "properties": {},
        }
        node["id"] = node_id
        node["type"] = node_type
        node["label"] = label
        node.setdefault("properties", {}).update(props or {})
        self.nodes[node_id] = node
        self._type_index.setdefault(node_type, [])
        if node_id not in self._type_index[node_type]:
            self._type_index[node_type].append(node_id)
        return node

    def add_edge(
        self,
        src: str,
        dst: str,
        relation: str,
        **props: Any,
    ) -> dict:
        """新增或更新有向边（自动确保两端节点存在——缺失时创建占位节点）。"""
        if not src or not dst:
            raise ValueError("边端点不能为空")
        if not relation:
            raise ValueError("relation 不能为空")
        if len(self.edges) >= MAX_EDGES:
            raise ValueError(
                f"图谱已达最大边数 {MAX_EDGES}；拒绝新增边 {src}→{dst}（fail-loud）"
            )
        # 自动补节点：缺失端点用关系名 + label 兜底
        if src not in self.nodes:
            self.add_node(src, "unknown", src)
        if dst not in self.nodes:
            self.add_node(dst, "unknown", dst)
        key = self._edge_key(src, dst, relation)
        edge = self.edges.get(key) or {
            "src": src,
            "dst": dst,
            "relation": relation,
            "properties": {},
        }
        edge["src"] = src
        edge["dst"] = dst
        edge["relation"] = relation
        edge.setdefault("properties", {}).update(props or {})
        self.edges[key] = edge
        self._out_index.setdefault(src, [])
        if key not in self._out_index[src]:
            self._out_index[src].append(key)
        self._in_index.setdefault(dst, [])
        if key not in self._in_index[dst]:
            self._in_index[dst].append(key)
        return edge

    # ------------------------------------------------------------------
    # 基础读取
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def get_edges(self, node_id: str) -> list[dict]:
        """返回与该节点相关的所有边（出边 + 入边）。"""
        out_keys = self._out_index.get(node_id, [])
        in_keys = self._in_index.get(node_id, [])
        result = [self.edges[k] for k in out_keys if k in self.edges]
        result.extend(self.edges[k] for k in in_keys if k in self.edges)
        return result

    def neighbors(
        self,
        node_id: str,
        relation: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        """返回邻居节点列表（可选按关系过滤、按方向过滤）。"""
        if direction not in ("in", "out", "both"):
            raise ValueError(f"direction 必须为 in/out/both，收到：{direction!r}")
        if node_id not in self.nodes:
            return []  # 不存在的节点返回空，避免误报 500
        result: list[dict] = []
        seen: set[str] = set()
        if direction in ("out", "both"):
            for key in self._out_index.get(node_id, []):
                e = self.edges.get(key)
                if not e:
                    continue
                if relation is not None and e["relation"] != relation:
                    continue
                if e["dst"] not in seen:
                    seen.add(e["dst"])
                    nb = self.nodes.get(e["dst"])
                    if nb:
                        result.append(nb)
        if direction in ("in", "both"):
            for key in self._in_index.get(node_id, []):
                e = self.edges.get(key)
                if not e:
                    continue
                if relation is not None and e["relation"] != relation:
                    continue
                if e["src"] not in seen:
                    seen.add(e["src"])
                    nb = self.nodes.get(e["src"])
                    if nb:
                        result.append(nb)
        return result

    # ------------------------------------------------------------------
    # 遍历
    # ------------------------------------------------------------------

    def bfs(
        self,
        start: str,
        max_depth: int = 2,
        relation: str | None = None,
    ) -> list[dict]:
        """广度优先遍历，返回从 start 出发可达的节点（含深度信息）。

        返回结构：[{id, depth, type, label, properties}]（不含 start 自身）。
        若 start 不存在，返回空列表。
        """
        if max_depth < 0:
            raise ValueError("max_depth 必须 ≥ 0")
        if start not in self.nodes:
            return []
        visited: dict[str, int] = {start: 0}
        queue: list[tuple[str, int]] = [(start, 0)]
        result: list[dict] = []
        while queue:
            cur_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for key in self._out_index.get(cur_id, []):
                e = self.edges.get(key)
                if not e:
                    continue
                if relation is not None and e["relation"] != relation:
                    continue
                nxt = e["dst"]
                if nxt in visited:
                    continue
                visited[nxt] = depth + 1
                node = self.nodes.get(nxt)
                if node:
                    result.append({
                        "id": nxt,
                        "depth": depth + 1,
                        "type": node["type"],
                        "label": node["label"],
                        "properties": node.get("properties", {}),
                    })
                    queue.append((nxt, depth + 1))
        return result

    def shortest_path(
        self,
        start: str,
        end: str,
        max_depth: int = 6,
        relation: str | None = None,
    ) -> list[str] | None:
        """BFS 最短路径。返回节点 id 序列（含 start 和 end）；无路径返回 None。"""
        if max_depth < 0:
            raise ValueError("max_depth 必须 ≥ 0")
        if start == end:
            return [start]
        if start not in self.nodes or end not in self.nodes:
            return None
        visited: set[str] = {start}
        prev: dict[str, str] = {}
        queue: list[tuple[str, int]] = [(start, 0)]
        while queue:
            cur_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for key in self._out_index.get(cur_id, []):
                e = self.edges.get(key)
                if not e:
                    continue
                if relation is not None and e["relation"] != relation:
                    continue
                nxt = e["dst"]
                if nxt in visited:
                    continue
                visited.add(nxt)
                prev[nxt] = cur_id
                if nxt == end:
                    path = [nxt]
                    while path[-1] != start:
                        path.append(prev[path[-1]])
                    path.reverse()
                    return path
                queue.append((nxt, depth + 1))
        return None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def query_by_type(self, node_type: str) -> list[dict]:
        return [self.nodes[nid] for nid in self._type_index.get(node_type, [])]

    def query_by_property(self, key: str, value: Any) -> list[dict]:
        out: list[dict] = []
        for node in self.nodes.values():
            props = node.get("properties") or {}
            # 精确匹配，字符串做归一化（去首尾空白）
            v = props.get(key)
            if isinstance(v, str) and isinstance(value, str):
                if v.strip() == value.strip():
                    out.append(node)
            elif v == value:
                out.append(node)
        return out

    # ------------------------------------------------------------------
    # 统计 / 序列化
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        type_dist: dict[str, int] = {}
        for node in self.nodes.values():
            t = node.get("type", "unknown")
            type_dist[t] = type_dist.get(t, 0) + 1
        rel_dist: dict[str, int] = {}
        for edge in self.edges.values():
            r = edge.get("relation", "unknown")
            rel_dist[r] = rel_dist.get(r, 0) + 1
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "type_distribution": dict(sorted(type_dist.items())),
            "relation_distribution": dict(sorted(rel_dist.items())),
            "meta": self.meta,
        }

    def serialize(self) -> dict:
        """序列化为可 JSON 化的 dict。"""
        return {
            "nodes": list(self.nodes.values()),
            "edges": list(self.edges.values()),
            "meta": self.meta or {},
        }

    @classmethod
    def deserialize(cls, data: dict) -> "KnowledgeGraph":
        """从序列化 dict 恢复图谱。容忍节点/边类型不严格。"""
        if not isinstance(data, dict):
            raise TypeError("deserialize 输入必须为 dict")
        g = cls(meta=data.get("meta") or {})
        for node in data.get("nodes") or []:
            if not isinstance(node, dict) or "id" not in node:
                continue
            g.nodes[node["id"]] = dict(node)
            g._type_index.setdefault(node.get("type", "unknown"), []).append(node["id"])
        for edge in data.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            if "src" not in edge or "dst" not in edge or "relation" not in edge:
                continue
            key = g._edge_key(edge["src"], edge["dst"], edge["relation"])
            g.edges[key] = dict(edge)
            g._out_index.setdefault(edge["src"], []).append(key)
            g._in_index.setdefault(edge["dst"], []).append(key)
        return g

    # ------------------------------------------------------------------
    # 便捷构造
    # ------------------------------------------------------------------

    def copy(self) -> "KnowledgeGraph":
        return self.deserialize(self.serialize())

    def __len__(self) -> int:
        return len(self.nodes)


# ----------------------------------------------------------------------
# 源数据加载与缓存
# ----------------------------------------------------------------------


class GraphRAGErrror(RuntimeError):
    """图谱不可用错误。"""


class GraphDataMissingError(GraphRAGErrror):
    """所有源数据文件缺失时抛出（fail-loud，不静默降级）。"""


def _load_json(path: Path) -> Any | None:
    """读 JSON 文件；缺失返回 None（由调用方决定降级或 fail-loud）。"""
    if not path.exists():
        logger.warning(f"[graphrag] 数据文件缺失，跳过: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # 文件在但损坏
        logger.warning(f"[graphrag] 数据文件 {path} 解析失败: {exc}")
        return None


def _resolve_cache_path() -> Path:
    """允许 HL_GRAPH_CACHE 覆盖缓存位置（部署/测试用）。"""
    override = os.getenv("HL_GRAPH_CACHE", "").strip()
    if override:
        return Path(override)
    return _GRAPH_CACHE_FILE


def build_from_sources() -> KnowledgeGraph:
    """从 data/ 加载所有源数据并构建知识图谱。

    容错策略：
    - 某个源文件缺失 → 跳过并 warning，继续构建其它源；
    - 全部源文件缺失 → 抛 GraphDataMissingError（fail-loud）。
    """
    # 延迟 import 避免与 builder 模块循环依赖
    from app.lib.graphrag_builder import (
        build_graph_from_axis_term_mapping,
        build_graph_from_classical_slices,
        build_graph_from_pulse_signatures,
        build_graph_from_tcm_pathway_map,
        build_graph_from_tcm_structured,
    )

    data_dir = _DATA_DIR  # 允许 monkeypatch 覆盖（测试用）

    tcm_shen_nong = _load_json(data_dir / "tcm_structured" / "神农本草经.json")
    tcm_shi_liao = _load_json(data_dir / "tcm_structured" / "食疗本草.json")
    classical_slices = _load_json(data_dir / "classical_slices.json")
    axis_term_mapping = _load_json(data_dir / "axis_term_mapping.json")
    pulse_signatures = _load_json(data_dir / "pulse_signatures.json")
    tcm_pathway_map = _load_json(data_dir / "tcm_pathway_map.json")

    # 全部缺失 → fail-loud（宁可显式不可用，也不交付空图）
    if not any([tcm_shen_nong, tcm_shi_liao, classical_slices,
                axis_term_mapping, pulse_signatures, tcm_pathway_map]):
        raise GraphDataMissingError(
            "所有知识图谱源数据文件均缺失或不可读；图谱不可用。"
            "已尝试目录: " + str(data_dir)
        )

    graph = KnowledgeGraph()
    source_count = 0

    # 1) 四向映射（轴/术语/通路）— 优先构建，为后续轴映射提供基础节点
    if axis_term_mapping:
        for item in build_graph_from_axis_term_mapping(axis_term_mapping):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    # 2) 通路映射（西医通路别名）
    if tcm_pathway_map:
        for item in build_graph_from_tcm_pathway_map(tcm_pathway_map):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    # 3) tcm_structured：神农本草经
    if tcm_shen_nong:
        for item in build_graph_from_tcm_structured(tcm_shen_nong, book="神农本草经"):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    # 4) tcm_structured：食疗本草
    if tcm_shi_liao:
        for item in build_graph_from_tcm_structured(tcm_shi_liao, book="食疗本草"):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    # 5) classical_slices：古籍切片（补轴映射 + from_text 边）
    if classical_slices:
        for item in build_graph_from_classical_slices(classical_slices):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    # 6) pulse_signatures：脉象节点 + 轴映射
    if pulse_signatures:
        for item in build_graph_from_pulse_signatures(pulse_signatures):
            kind, payload = item
            if kind == "node":
                node_id, node_type, label, props = payload
                graph.add_node(node_id, node_type, label, **(props or {}))
            else:
                src, dst, relation, props = payload
                graph.add_edge(src, dst, relation, **(props or {}))
        source_count += 1

    graph.meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_count": source_count,
        "version": "graphrag/v1",
        "wellness_disclaimer": (
            "本图谱仅供健康管理参考，不构成专业健康建议。"
        ),
    }
    logger.info(
        "[graphrag] 图谱构建完成：nodes=%d edges=%d sources=%d",
        len(graph.nodes), len(graph.edges), source_count,
    )
    return graph


def load_graph(rebuild: bool = False) -> KnowledgeGraph:
    """加载图谱：优先读缓存；缓存缺失或 rebuild=True 时从源数据重建。"""
    cache_path = _resolve_cache_path()
    if not rebuild and cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            graph = KnowledgeGraph.deserialize(data)
            logger.info(
                "[graphrag] 从缓存加载图谱: %s (nodes=%d, edges=%d)",
                cache_path, len(graph.nodes), len(graph.edges),
            )
            return graph
        except Exception as exc:
            logger.warning(f"[graphrag] 缓存加载失败，将重建: {exc}")

    graph = build_from_sources()
    # 尝试写回缓存（失败不阻塞）
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(graph.serialize(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[graphrag] 图谱已写入缓存: {cache_path}")
    except Exception as exc:
        logger.warning(f"[graphrag] 写入缓存失败（不影响本次使用）: {exc}")
    return graph


# ----------------------------------------------------------------------
# 进程级缓存（同进程内多次调用不重复读盘）
# ----------------------------------------------------------------------

_GRAPH_CACHE: KnowledgeGraph | None = None


def get_graph(rebuild: bool = False) -> KnowledgeGraph:
    """进程级懒加载图谱。"""
    global _GRAPH_CACHE
    if _GRAPH_CACHE is None or rebuild:
        _GRAPH_CACHE = load_graph(rebuild=rebuild)
    return _GRAPH_CACHE
