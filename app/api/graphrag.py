"""GraphRAG 图查询 API（S2-5）

端点分两类：
- 公开：stats / nodes / neighbors / search（结构查询，无用户数据）
- 登录：query / axes/{id}/related / herb/{id}/profile（涉及路径推演或完整画像）

wellness 边界：所有响应带 wellness_disclaimer；不使用诊断/治疗/患者类词汇。
fail-loud：节点不存在返回 404，查询参数无效返回 400。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.lib.graphrag_engine import (
    GraphDataMissingError,
    get_graph,
)
from app.models.user import User

router = APIRouter(tags=["知识图谱"])

WELLNESS_DISCLAIMER = (
    "本图谱仅供健康管理参考，不构成专业健康建议。"
)


# ---------------------------------------------------------------------------
# 请求/响应 Schema
# ---------------------------------------------------------------------------


class PathQueryRequest(BaseModel):
    start: str = Field(..., min_length=1, description="起始节点 id")
    end: str = Field(..., min_length=1, description="目标节点 id")
    max_depth: int = Field(default=6, ge=1, le=12, description="最大搜索深度")
    relation: str | None = Field(default=None, description="可选：仅遍历指定关系")


class NeighborQueryParams(BaseModel):
    direction: str = Field(default="both", pattern=r"^(in|out|both)$")
    relation: str | None = None


# ---------------------------------------------------------------------------
# 公共辅助
# ---------------------------------------------------------------------------


def _get_graph_or_404():
    """取图谱；源数据全缺时返回 503（fail-loud，明确说明不可用）。"""
    try:
        return get_graph()
    except GraphDataMissingError as exc:
        logger.error(f"[graphrag] 图谱不可用: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"知识图谱不可用: {exc}",
        )
    except Exception as exc:  # 其它构建失败
        logger.error(f"[graphrag] 图谱加载异常: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"知识图谱加载失败: {exc}",
        )


def _node_payload(node: dict) -> dict:
    """统一节点响应格式（保留 id/type/label/properties）。"""
    return {
        "id": node["id"],
        "type": node.get("type"),
        "label": node.get("label"),
        "properties": node.get("properties") or {},
    }


# ---------------------------------------------------------------------------
# 公开端点
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=dict)
async def get_stats():
    """图谱统计：节点/边数、类型分布、关系分布。"""
    graph = _get_graph_or_404()
    stats = graph.stats()
    return {
        "success": True,
        **stats,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


@router.get("/nodes/{node_id}", response_model=dict)
async def get_node(node_id: str):
    """查询单个节点详情。不存在返回 404。"""
    graph = _get_graph_or_404()
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"节点不存在: {node_id}",
        )
    return {
        "success": True,
        "node": _node_payload(node),
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


@router.get("/nodes/{node_id}/neighbors", response_model=dict)
async def get_neighbors(
    node_id: str,
    direction: str = Query("both", pattern=r"^(in|out|both)$", description="查询方向"),
    relation: str | None = Query(None, description="按关系过滤"),
):
    """查询邻居节点。节点不存在返回 404（fail-loud）。"""
    graph = _get_graph_or_404()
    if node_id not in graph.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"节点不存在: {node_id}",
        )
    try:
        neighbors = graph.neighbors(node_id, relation=relation, direction=direction)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return {
        "success": True,
        "node_id": node_id,
        "count": len(neighbors),
        "neighbors": [_node_payload(n) for n in neighbors],
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


@router.get("/search", response_model=dict)
async def search_nodes(
    q: str = Query(..., min_length=1, description="查询关键词（按 label 或 id 匹配）"),
    type: str | None = Query(None, description="按节点类型过滤"),
    limit: int = Query(20, ge=1, le=200, description="返回数量上限"),
):
    """关键词搜索节点：匹配 id 或 label（大小写不敏感）。"""
    graph = _get_graph_or_404()
    q_norm = q.strip().lower()
    if not q_norm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="查询关键词不能为空",
        )
    valid_types = set(n.get("type") for n in graph.nodes.values())
    if type and type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知节点类型: {type}；可选: {sorted(valid_types)}",
        )
    results: list[dict] = []
    for node in graph.nodes.values():
        if type and node.get("type") != type:
            continue
        if q_norm in str(node.get("id", "")).lower() or \
           q_norm in str(node.get("label", "")).lower():
            results.append(_node_payload(node))
            if len(results) >= limit:
                break
    return {
        "success": True,
        "query": q,
        "type": type,
        "count": len(results),
        "results": results,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# 登录端点
# ---------------------------------------------------------------------------


@router.post("/query", response_model=dict)
async def query_path(
    body: PathQueryRequest,
    current_user: User = Depends(get_current_user),
):
    """路径查询：返回 start→end 的最短路径（BFS）。"""
    graph = _get_graph_or_404()
    start_exists = body.start in graph.nodes
    end_exists = body.end in graph.nodes
    if not start_exists or not end_exists:
        missing = []
        if not start_exists:
            missing.append(body.start)
        if not end_exists:
            missing.append(body.end)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"节点不存在: {missing}",
        )
    try:
        path = graph.shortest_path(
            body.start, body.end,
            max_depth=body.max_depth,
            relation=body.relation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if path is None:
        return {
            "success": True,
            "found": False,
            "start": body.start,
            "end": body.end,
            "max_depth": body.max_depth,
            "relation": body.relation,
            "path": [],
            "wellness_disclaimer": WELLNESS_DISCLAIMER,
        }

    # 组装路径细节
    path_nodes = [_node_payload(graph.nodes[nid]) for nid in path if nid in graph.nodes]
    # 收集路径上的边
    path_edges: list[dict] = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        for edge in graph.get_edges(a):
            if edge["dst"] == b and (body.relation is None or edge["relation"] == body.relation):
                path_edges.append({
                    "src": edge["src"],
                    "dst": edge["dst"],
                    "relation": edge["relation"],
                    "properties": edge.get("properties") or {},
                })
                break
    logger.info(
        f"[graphrag] 路径查询 | user_id={current_user.id} | "
        f"{body.start} → {body.end} | depth={len(path)}"
    )
    return {
        "success": True,
        "found": True,
        "start": body.start,
        "end": body.end,
        "max_depth": body.max_depth,
        "relation": body.relation,
        "depth": len(path),
        "path": path,
        "nodes": path_nodes,
        "edges": path_edges,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


@router.get("/axes/{axis_id}/related", response_model=dict)
async def get_axis_related(
    axis_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询某轴关联的所有 herb/food/pulse 节点。"""
    graph = _get_graph_or_404()
    axis_id_norm = axis_id.strip().upper()
    if axis_id_norm not in {"A", "B", "C", "D", "E", "F", "G", "H"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知轴: {axis_id}；合法轴为 A-H",
        )
    axis_node_id = f"axis:{axis_id_norm}"
    axis_node = graph.get_node(axis_node_id)
    if not axis_node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"轴节点不存在: {axis_node_id}",
        )

    # 入边指向轴节点的关系边（axis_of）
    related: list[dict] = []
    seen_ids: set[str] = set()
    for edge in graph.get_edges(axis_node_id):
        if edge["relation"] != "axis_of":
            continue
        if edge["dst"] != axis_node_id:
            continue  # 只算指向本轴的边
        src = edge["src"]
        if src in seen_ids:
            continue
        seen_ids.add(src)
        node = graph.get_node(src)
        if node and node.get("type") in ("herb", "food", "pulse"):
            related.append({
                "node": _node_payload(node),
                "edge_properties": edge.get("properties") or {},
            })

    # 分类型聚合
    by_type: dict[str, list] = {"herb": [], "food": [], "pulse": []}
    for entry in related:
        node_type = entry["node"]["type"]
        if node_type in by_type:
            by_type[node_type].append(entry["node"]["id"])

    logger.info(
        f"[graphrag] 轴关联查询 | user_id={current_user.id} | axis={axis_id_norm} | "
        f"herb={len(by_type['herb'])} food={len(by_type['food'])} pulse={len(by_type['pulse'])}"
    )
    return {
        "success": True,
        "axis_id": axis_id_norm,
        "axis": _node_payload(axis_node),
        "counts": {
            "herb": len(by_type["herb"]),
            "food": len(by_type["food"]),
            "pulse": len(by_type["pulse"]),
            "total": len(related),
        },
        "related": related,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


@router.get("/herb/{herb_id}/profile", response_model=dict)
async def get_herb_profile(
    herb_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询某药材完整画像：属性 + 关联轴 + 出处 + 治疗意向（efficacy）。"""
    graph = _get_graph_or_404()
    # 支持两种调用方式：完整节点 id 或裸药材名（自动补齐前缀）
    node = graph.get_node(herb_id)
    if not node:
        # 尝试从 search 定位（限定 herb/food 类型）
        herb_id_lower = herb_id.strip().lower()
        for candidate in graph.query_by_type("herb") + graph.query_by_type("food"):
            if herb_id_lower == str(candidate.get("label", "")).lower() or \
               herb_id_lower in str(candidate["id"]).lower():
                node = candidate
                break

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"药材不存在: {herb_id}",
        )
    node_id = node["id"]

    edges = graph.get_edges(node_id)

    def _group_by_rel(rel: str, direction: str = "out") -> list[dict]:
        out = []
        for edge in edges:
            if edge["relation"] != rel:
                continue
            if direction == "out" and edge["src"] != node_id:
                continue
            if direction == "in" and edge["dst"] != node_id:
                continue
            out.append({
                "src": edge["src"],
                "dst": edge["dst"],
                "relation": edge["relation"],
                "properties": edge.get("properties") or {},
            })
        return out

    def _resolve(id_: str) -> dict | None:
        n = graph.get_node(id_)
        return _node_payload(n) if n else None

    axes = [
        {"node": _resolve(e["dst"]), "edge": e}
        for e in _group_by_rel("axis_of")
    ]
    axes = [a for a in axes if a["node"]]
    conditions = [
        {"node": _resolve(e["dst"]), "edge": e}
        for e in _group_by_rel("treats")
    ]
    conditions = [c for c in conditions if c["node"]]
    sources = [
        {"node": _resolve(e["dst"]), "edge": e}
        for e in _group_by_rel("from_text")
    ]
    sources = [s for s in sources if s["node"]]
    related_herbs = [
        {"node": _resolve(e["src"] if e["dst"] == node_id else e["dst"]), "edge": e}
        for e in _group_by_rel("relates_to")
    ]
    related_herbs = [r for r in related_herbs if r["node"]]

    logger.info(
        f"[graphrag] 药材画像 | user_id={current_user.id} | herb={node_id} | "
        f"axes={len(axes)} conditions={len(conditions)} sources={len(sources)}"
    )
    return {
        "success": True,
        "herb": _node_payload(node),
        "axes": axes,
        "conditions": conditions,
        "sources": sources,
        "related_herbs": related_herbs,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }
