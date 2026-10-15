"""GraphRAG 知识图谱测试（S2-5）

覆盖：
- KnowledgeGraph 基本操作（add_node/add_edge/get_node/get_edges）
- neighbors 查询（direction in/out/both，relation 过滤）
- BFS 遍历 + shortest_path（深度限制 / 无路径 / 关系过滤）
- query_by_type / query_by_property
- stats 统计
- serialize/deserialize 往返
- build_from_sources 全量构建
- 各源数据构建器
- API 端点（公开 + 登录）
- 边界值（空图 / 不存在节点 / 越界参数）
- fail-loud（源数据全缺 → 503；节点不存在 → 404）
"""
import json
import os
from pathlib import Path

import pytest

from app.lib.graphrag_builder import (
    build_graph_from_axis_term_mapping,
    build_graph_from_classical_slices,
    build_graph_from_pulse_signatures,
    build_graph_from_tcm_pathway_map,
    build_graph_from_tcm_structured,
)
from app.lib.graphrag_engine import (
    KnowledgeGraph,
    GraphDataMissingError,
    build_from_sources,
    load_graph,
)


# ---------------------------------------------------------------------------
# 构造辅助：一个小型可复现测试图
# ---------------------------------------------------------------------------


def _small_graph() -> KnowledgeGraph:
    """构造小型图，覆盖所有关系与方向组合。"""
    g = KnowledgeGraph()
    g.add_node("herb:gn", "herb", "甘草", book="神农本草经", property="甘平")
    g.add_node("herb:hg", "herb", "黄芪", book="神农本草经")
    g.add_node("herb:dq", "herb", "当归", book="神农本草经")
    g.add_node("axis:A", "axis", "气化轴", axis_id="A")
    g.add_node("axis:F", "axis", "正邪轴", axis_id="F")
    g.add_node("cond:shu", "condition", "发热")
    g.add_node("cond:pi", "condition", "气虚")
    g.add_node("text:sn:gn", "classical_text", "神农本草经·甘草")
    g.add_node("pulse:fu", "pulse", "浮脉")
    g.add_node("pathway:ampk", "pathway", "AMPK")
    g.add_node("term:qi", "term", "气化")

    g.add_edge("herb:gn", "axis:A", "axis_of", confidence=0.8)
    g.add_edge("herb:hg", "axis:A", "axis_of", confidence=0.7)
    g.add_edge("herb:hg", "axis:F", "axis_of", confidence=0.6)
    g.add_edge("herb:dq", "axis:F", "axis_of", confidence=0.9)
    g.add_edge("herb:gn", "cond:shu", "treats")
    g.add_edge("herb:hg", "cond:pi", "treats")
    g.add_edge("herb:gn", "text:sn:gn", "from_text")
    g.add_edge("herb:gn", "herb:hg", "relates_to", reason="药对")
    g.add_edge("pulse:fu", "axis:A", "axis_of")
    g.add_edge("term:qi", "axis:A", "maps_to")
    g.add_edge("axis:A", "pathway:ampk", "maps_to")
    return g


# ---------------------------------------------------------------------------
# KnowledgeGraph 基本操作
# ---------------------------------------------------------------------------


def test_add_node_and_get():
    g = KnowledgeGraph()
    node = g.add_node("n1", "herb", "甘草", book="神农本草经")
    assert node["id"] == "n1"
    assert node["type"] == "herb"
    assert node["label"] == "甘草"
    assert node["properties"]["book"] == "神农本草经"
    fetched = g.get_node("n1")
    assert fetched is node


def test_add_node_empty_id_raises():
    g = KnowledgeGraph()
    with pytest.raises(ValueError, match="node_id"):
        g.add_node("", "herb", "x")


def test_add_node_empty_type_raises():
    g = KnowledgeGraph()
    with pytest.raises(ValueError, match="node_type"):
        g.add_node("n1", "", "x")


def test_add_node_empty_label_raises():
    g = KnowledgeGraph()
    with pytest.raises(ValueError, match="label"):
        g.add_node("n1", "herb", "")


def test_add_node_updates_existing():
    g = KnowledgeGraph()
    g.add_node("n1", "herb", "甘草", property="甘平")
    g.add_node("n1", "herb", "甘草", evidence="high")
    n = g.get_node("n1")
    assert n["properties"]["property"] == "甘平"
    assert n["properties"]["evidence"] == "high"


def test_add_edge_creates_missing_endpoints():
    g = KnowledgeGraph()
    g.add_edge("a", "b", "relates_to")
    assert g.get_node("a") is not None
    assert g.get_node("b") is not None
    assert g.get_node("a")["type"] == "unknown"


def test_add_edge_empty_relation_raises():
    g = KnowledgeGraph()
    g.add_node("a", "herb", "A")
    g.add_node("b", "herb", "B")
    with pytest.raises(ValueError, match="relation"):
        g.add_edge("a", "b", "")


def test_add_edge_empty_endpoint_raises():
    g = KnowledgeGraph()
    with pytest.raises(ValueError, match="边端点"):
        g.add_edge("", "b", "r")
    with pytest.raises(ValueError, match="边端点"):
        g.add_edge("a", "", "r")


def test_add_edge_upserts_existing():
    g = KnowledgeGraph()
    g.add_edge("a", "b", "r", weight=1)
    g.add_edge("a", "b", "r", weight=2)
    edge = list(g.edges.values())[0]
    assert edge["properties"]["weight"] == 2


def test_get_edges_returns_both_in_and_out():
    g = _small_graph()
    # herb:hg 关联：出边 axis_of(A) + axis_of(F) + treats(pi)，入边 relates_to(来自 herb:gn)
    edges = g.get_edges("herb:hg")
    assert len(edges) == 4
    rels = {e["relation"] for e in edges}
    assert rels == {"axis_of", "treats", "relates_to"}
    # 精确核对边数分布
    from collections import Counter
    cnt = Counter(e["relation"] for e in edges)
    assert cnt["axis_of"] == 2
    assert cnt["treats"] == 1
    assert cnt["relates_to"] == 1


def test_get_edges_unknown_node_returns_empty():
    g = KnowledgeGraph()
    assert g.get_edges("not_exist") == []


def test_get_node_unknown_returns_none():
    g = KnowledgeGraph()
    assert g.get_node("nope") is None


def test_empty_graph_len():
    g = KnowledgeGraph()
    assert len(g) == 0
    assert g.stats()["node_count"] == 0
    assert g.stats()["edge_count"] == 0


# ---------------------------------------------------------------------------
# neighbors
# ---------------------------------------------------------------------------


def test_neighbors_out_only():
    g = _small_graph()
    nbs = g.neighbors("herb:gn", direction="out")
    labels = {n["label"] for n in nbs}
    assert "气化轴" in labels  # axis:A
    assert "发热" in labels    # cond:shu
    assert "神农本草经·甘草" in labels  # text
    assert "黄芪" in labels    # herb:hg (relates_to)


def test_neighbors_in_only():
    g = _small_graph()
    nbs = g.neighbors("axis:A", direction="in")
    labels = {n["label"] for n in nbs}
    assert "甘草" in labels
    assert "黄芪" in labels
    assert "浮脉" in labels
    assert "气化" in labels


def test_neighbors_both_dedupes():
    g = KnowledgeGraph()
    g.add_node("a", "n", "A")
    g.add_node("b", "n", "B")
    g.add_edge("a", "b", "r")
    g.add_edge("b", "a", "r")  # 双向
    nbs = g.neighbors("a", direction="both")
    assert len(nbs) == 1
    assert nbs[0]["id"] == "b"


def test_neighbors_relation_filter():
    g = _small_graph()
    nbs = g.neighbors("axis:A", direction="in", relation="axis_of")
    labels = {n["label"] for n in nbs}
    assert "甘草" in labels
    assert "黄芪" in labels
    assert "浮脉" in labels
    assert "气化" not in labels  # term:qi 是 maps_to


def test_neighbors_bad_direction_raises():
    g = _small_graph()
    with pytest.raises(ValueError, match="direction"):
        g.neighbors("herb:gn", direction="sideways")


def test_neighbors_unknown_node_returns_empty():
    g = _small_graph()
    assert g.neighbors("not_exist") == []


# ---------------------------------------------------------------------------
# BFS
# ---------------------------------------------------------------------------


def test_bfs_reachable():
    g = _small_graph()
    result = g.bfs("herb:gn", max_depth=2)
    ids = {r["id"] for r in result}
    assert "axis:A" in ids
    assert "cond:shu" in ids
    assert "text:sn:gn" in ids
    assert "herb:hg" in ids  # relates_to


def test_bfs_depth_limit():
    g = _small_graph()
    depth_1 = g.bfs("herb:gn", max_depth=1)
    ids_1 = {r["id"] for r in depth_1}
    # 直接邻居：axis:A, cond:shu, text, herb:hg
    assert "axis:A" in ids_1
    # 二级才有的邻居（axis:A → pathway:ampk）
    depth_2 = g.bfs("herb:gn", max_depth=2)
    ids_2 = {r["id"] for r in depth_2}
    assert "pathway:ampk" in ids_2
    assert "pathway:ampk" not in ids_1


def test_bfs_relation_filter():
    g = _small_graph()
    result = g.bfs("herb:gn", max_depth=3, relation="axis_of")
    ids = {r["id"] for r in result}
    assert "axis:A" in ids
    # treats / from_text / relates_to 应被过滤
    assert "cond:shu" not in ids
    assert "text:sn:gn" not in ids


def test_bfs_unknown_start_returns_empty():
    g = _small_graph()
    assert g.bfs("not_exist") == []


def test_bfs_zero_depth_returns_empty():
    g = _small_graph()
    # max_depth=0 应返回空（不遍历）
    assert g.bfs("herb:gn", max_depth=0) == []


def test_bfs_negative_depth_raises():
    g = _small_graph()
    with pytest.raises(ValueError, match="max_depth"):
        g.bfs("herb:gn", max_depth=-1)


def test_bfs_result_structure():
    g = _small_graph()
    r = g.bfs("herb:gn", max_depth=1)
    assert len(r) > 0
    sample = r[0]
    assert {"id", "depth", "type", "label", "properties"} <= set(sample)
    assert sample["depth"] == 1


def test_shortest_path_direct():
    g = _small_graph()
    path = g.shortest_path("herb:gn", "axis:A")
    assert path == ["herb:gn", "axis:A"]


def test_shortest_path_multi_hop():
    g = _small_graph()
    path = g.shortest_path("herb:gn", "pathway:ampk")
    assert path is not None
    assert path[0] == "herb:gn"
    assert path[-1] == "pathway:ampk"
    assert len(path) >= 2


def test_shortest_path_no_path_returns_none():
    g = KnowledgeGraph()
    g.add_node("a", "n", "A")
    g.add_node("b", "n", "B")
    assert g.shortest_path("a", "b") is None


def test_shortest_path_self():
    g = _small_graph()
    path = g.shortest_path("herb:gn", "herb:gn")
    assert path == ["herb:gn"]


def test_shortest_path_unknown_endpoint_returns_none():
    g = _small_graph()
    assert g.shortest_path("herb:gn", "nope") is None
    assert g.shortest_path("nope", "herb:gn") is None


def test_shortest_path_depth_limit_blocks():
    g = _small_graph()
    # herb:gn → axis:A → pathway:ampk 是 2 跳
    # 限制 max_depth=1 时不可达
    assert g.shortest_path("herb:gn", "pathway:ampk", max_depth=1) is None


def test_shortest_path_relation_filter():
    g = _small_graph()
    # 用 axis_of 关系搜索 herb:gn → axis:F 不可达（herb:gn 只指向 axis:A）
    assert g.shortest_path("herb:gn", "axis:F", relation="axis_of") is None


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def test_query_by_type():
    g = _small_graph()
    herbs = g.query_by_type("herb")
    assert {n["id"] for n in herbs} == {"herb:gn", "herb:hg", "herb:dq"}


def test_query_by_type_unknown_returns_empty():
    g = _small_graph()
    assert g.query_by_type("nonexistent") == []


def test_query_by_property_exact():
    g = _small_graph()
    result = g.query_by_property("axis_id", "A")
    assert len(result) >= 1
    assert any(n["id"] == "axis:A" for n in result)


def test_query_by_property_string_normalized():
    g = KnowledgeGraph()
    g.add_node("a", "n", "A", code=" X ")
    g.add_node("b", "n", "B", code="X")
    result = g.query_by_property("code", "X")
    assert len(result) == 2


def test_query_by_property_missing_returns_empty():
    g = _small_graph()
    assert g.query_by_property("nonexistent_key", "value") == []


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def test_stats_structure():
    g = _small_graph()
    stats = g.stats()
    # _small_graph 有 11 个节点、11 条边
    assert stats["node_count"] == 11
    assert stats["edge_count"] == 11
    assert "axis" in stats["type_distribution"]
    assert "herb" in stats["type_distribution"]
    assert "axis_of" in stats["relation_distribution"]
    assert "maps_to" in stats["relation_distribution"]


def test_stats_meta_included():
    g = KnowledgeGraph(meta={"version": "test"})
    stats = g.stats()
    assert stats["meta"] == {"version": "test"}


def test_stats_empty_graph():
    g = KnowledgeGraph()
    stats = g.stats()
    assert stats["node_count"] == 0
    assert stats["edge_count"] == 0
    assert stats["type_distribution"] == {}
    assert stats["relation_distribution"] == {}


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def test_serialize_deserialize_roundtrip():
    g = _small_graph()
    data = g.serialize()
    assert "nodes" in data and "edges" in data and "meta" in data
    g2 = KnowledgeGraph.deserialize(data)
    assert g2.stats()["node_count"] == g.stats()["node_count"]
    assert g2.stats()["edge_count"] == g.stats()["edge_count"]
    # 抽样验证
    n1 = g.get_node("herb:gn")
    n2 = g2.get_node("herb:gn")
    assert n1["type"] == n2["type"]
    assert n1["label"] == n2["label"]
    assert n1["properties"] == n2["properties"]


def test_serialize_json_roundtrip():
    g = _small_graph()
    data = g.serialize()
    s = json.dumps(data, ensure_ascii=False)
    data2 = json.loads(s)
    g2 = KnowledgeGraph.deserialize(data2)
    assert g2.stats()["node_count"] == g.stats()["node_count"]


def test_deserialize_rejects_non_dict():
    with pytest.raises(TypeError):
        KnowledgeGraph.deserialize([])


def test_deserialize_tolerates_bad_entries():
    data = {
        "nodes": [{"id": "a", "type": "n", "label": "A"}, {"id": 1}, "not_a_dict", {"id": "b"}],
        "edges": [
            {"src": "a", "dst": "b", "relation": "r"},
            {"src": "a"},  # 缺 dst/relation
            "not_a_dict",
        ],
    }
    g = KnowledgeGraph.deserialize(data)
    # 只有带 id 的 dict 才算节点（"not_a_dict" 和 {"id":1} 被跳过）
    assert g.get_node("a") is not None
    assert g.get_node("b") is not None
    # 只有完整的边才算
    assert len(g.edges) == 1


def test_copy_is_deep():
    g = _small_graph()
    g2 = g.copy()
    assert g is not g2
    # 修改副本不影响原图
    g2.add_node("new", "n", "New")
    assert "new" not in g.nodes


# ---------------------------------------------------------------------------
# build_from_sources 全量构建
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def full_graph():
    """模块级共享的全量图谱（构建一次，多测试复用）。"""
    return build_from_sources()


def test_full_build_nonempty(full_graph):
    assert full_graph.stats()["node_count"] > 500
    assert full_graph.stats()["edge_count"] > 500


def test_full_build_has_core_node_types(full_graph):
    types = set(full_graph.stats()["type_distribution"])
    for t in ("herb", "axis", "pulse", "term", "pathway", "classical_text", "condition"):
        assert t in types, f"缺少节点类型: {t}"


def test_full_build_has_core_relations(full_graph):
    rels = set(full_graph.stats()["relation_distribution"])
    for r in ("axis_of", "treats", "from_text", "maps_to", "relates_to"):
        assert r in rels, f"缺少关系: {r}"


def test_full_build_meta(full_graph):
    meta = full_graph.meta
    assert meta.get("source_count", 0) >= 4
    assert meta.get("version") == "graphrag/v1"
    assert meta.get("built_at")
    # wellness 边界声明必须存在（中文文案）
    disclaimer = meta.get("wellness_disclaimer", "")
    assert disclaimer
    assert "健康管理" in disclaimer or "参考" in disclaimer


def test_full_build_has_8_axes(full_graph):
    axes = full_graph.query_by_type("axis")
    axis_ids = {n["properties"]["axis_id"] for n in axes if n.get("properties", {}).get("axis_id")}
    assert {"A", "B", "C", "D", "E", "F", "G", "H"} <= axis_ids


def test_full_build_herbs_include_shen_nong(full_graph):
    herbs = full_graph.query_by_type("herb")
    labels = {n["label"] for n in herbs}
    # 神农本草经典型药材
    assert "丹沙" in labels
    assert "云母" in labels


def test_full_build_herbs_include_shi_liao(full_graph):
    herbs = full_graph.query_by_type("herb")
    labels = {n["label"] for n in herbs}
    # 食疗本草里常见：盐
    assert "盐" in labels


def test_full_build_pulses(full_graph):
    pulses = full_graph.query_by_type("pulse")
    assert len(pulses) >= 20
    labels = {n["label"] for n in pulses}
    assert "浮脉" in labels


# ---------------------------------------------------------------------------
# 各源数据构建器
# ---------------------------------------------------------------------------


def test_builder_tcm_structured_herbs():
    data = {
        "book": "测试本草",
        "author": "作者",
        "dynasty": "唐",
        "entities": [
            {"type": "herb", "name": "甘草", "property": "甘平", "efficacy": "祛痰", "source_quote": "味甘，平。"},
        ],
    }
    items = build_graph_from_tcm_structured(data, book="测试本草")
    node_items = [i for i in items if i[0] == "node"]
    edge_items = [i for i in items if i[0] == "edge"]
    node_ids = {i[1][0] for i in node_items}
    assert "herb:测试本草:甘草" in node_ids
    assert "condition:祛痰" in node_ids
    assert "text:测试本草:甘草" in node_ids
    assert len(edge_items) == 2  # treats + from_text


def test_builder_tcm_structured_food():
    data = {
        "book": "食疗本草",
        "entities": [
            {"type": "food_therapy", "name": "盐", "property": None, "efficacy": "消肿"},
        ],
    }
    items = build_graph_from_tcm_structured(data, book="食疗本草")
    node_items = [i for i in items if i[0] == "node"]
    node_ids = {i[1][0] for i in node_items}
    assert "food:食疗本草:盐" in node_ids


def test_builder_tcm_structured_empty():
    assert build_graph_from_tcm_structured({"book": "空", "entities": []}) == []


def test_builder_tcm_structured_skips_bad_entries():
    data = {
        "book": "测试",
        "entities": [None, {}, {"name": "", "type": "herb"}, "not_a_dict"],
    }
    items = build_graph_from_tcm_structured(data)
    # 只有 name 非空的 entry 才产节点
    node_items = [i for i in items if i[0] == "node"]
    assert len(node_items) == 0


def test_builder_classical_slices_axis_of():
    data = {
        "slices": [
            {
                "book": "神农本草经",
                "entity": "丹沙",
                "entity_type": "herb",
                "axis_hint": "F",
                "axis_hint_secondary": "G",
                "axis_confidence": 0.54,
                "passage": "味甘，微寒。",
                "evidence_level": "high",
            }
        ]
    }
    items = build_graph_from_classical_slices(data)
    edges = [i for i in items if i[0] == "edge"]
    edge_keys = {(e[1][0], e[1][1], e[1][2]) for e in edges}
    # axis_of 指向 axis:F 和 axis:G
    assert ("herb:神农本草经:丹沙", "axis:F", "axis_of") in edge_keys
    assert ("herb:神农本草经:丹沙", "axis:G", "axis_of") in edge_keys


def test_builder_classical_slices_axis_normalization():
    """axis_hint 可能是 'F' 或 'F正邪'——都应提取出 F。"""
    data = {
        "slices": [
            {"book": "B", "entity": "E", "entity_type": "herb", "axis_hint": "F正邪"},
            {"book": "B", "entity": "E2", "entity_type": "herb", "axis_hint": "A气化"},
        ]
    }
    items = build_graph_from_classical_slices(data)
    edges = [i for i in items if i[0] == "edge"]
    edge_keys = {(e[1][1], e[1][2]) for e in edges}
    assert ("axis:F", "axis_of") in edge_keys
    assert ("axis:A", "axis_of") in edge_keys


def test_builder_classical_slices_skips_empty():
    data = {"slices": [None, {}, {"book": "", "entity": "X"}, {"book": "B", "entity": ""}]}
    items = build_graph_from_classical_slices(data)
    # 只有 book+entity 都非空才产节点
    node_items = [i for i in items if i[0] == "node"]
    assert len(node_items) == 0


def test_builder_classical_slices_dedup_edges():
    """同一 (src, dst, relation) 不应重复添加边。"""
    data = {
        "slices": [
            {"book": "B", "entity": "E", "entity_type": "herb", "axis_hint": "F"},
            {"book": "B", "entity": "E", "entity_type": "herb", "axis_hint": "F"},
        ]
    }
    items = build_graph_from_classical_slices(data)
    edges = [i for i in items if i[0] == "edge" and i[1][2] == "axis_of"]
    keys = {(e[1][0], e[1][1]) for e in edges}
    assert len(keys) == 1  # 只有一条 axis_of 边


def test_builder_pulse_signatures_creates_pulse_nodes():
    data = {
        "pulses": [
            {"id": "fu", "name": "浮脉", "category": "位", "axes": ["A气化", "F正邪"]},
            {"id": "chen", "name": "沉脉", "category": "位", "axes": ["B气血"]},
        ]
    }
    items = build_graph_from_pulse_signatures(data)
    nodes = [i for i in items if i[0] == "node"]
    node_ids = {n[1][0] for n in nodes}
    assert "pulse:fu" in node_ids
    assert "pulse:chen" in node_ids
    assert "axis:A" in node_ids
    assert "axis:F" in node_ids
    assert "axis:B" in node_ids


def test_builder_pulse_signatures_empty():
    assert build_graph_from_pulse_signatures({"pulses": []}) == []


def test_builder_pulse_signatures_skips_bad():
    items = build_graph_from_pulse_signatures({"pulses": [None, {}, {"name": "无 id"}]})
    nodes = [i for i in items if i[0] == "node"]
    # 只有 id 非空的才产节点
    node_ids = {n[1][0] for n in nodes}
    assert "pulse:" not in "".join(node_ids)  # 空 id 被跳过


def test_builder_axis_term_mapping_creates_axes_terms_pathways():
    data = {
        "axes": {
            "A": {
                "axis_label": "气化轴",
                "gbt_20348_2026": {"zh": "气化", "en": "Qi", "note": "n"},
                "pathways": ["autophagy", "ampk_signaling"],
                "classical_books": ["神农本草经"],
            }
        }
    }
    items = build_graph_from_axis_term_mapping(data)
    node_items = [i for i in items if i[0] == "node"]
    node_ids = {n[1][0] for n in node_items}
    assert "axis:A" in node_ids
    assert "term:气化" in node_ids
    assert "pathway:autophagy" in node_ids
    assert "pathway:ampk_signaling" in node_ids
    assert "text:神农本草经" in node_ids


def test_builder_axis_term_mapping_maps_to_edges():
    data = {
        "axes": {
            "B": {
                "axis_label": "气血轴",
                "gbt_20348_2026": {"zh": "气血"},
                "pathways": ["mitochondrial"],
            }
        }
    }
    items = build_graph_from_axis_term_mapping(data)
    edges = [i for i in items if i[0] == "edge"]
    edge_keys = {(e[1][0], e[1][1], e[1][2]) for e in edges}
    assert ("term:气血", "axis:B", "maps_to") in edge_keys
    assert ("term:气血", "pathway:mitochondrial", "maps_to") in edge_keys


def test_builder_axis_term_mapping_skips_bad():
    data = {"axes": {"A": None, "B": {"axis_label": ""}}}
    items = build_graph_from_axis_term_mapping(data)
    nodes = [i for i in items if i[0] == "node"]
    node_ids = {n[1][0] for n in nodes}
    # B 轴无 axis_label 但 axis_id 有 → 仍应产 axis:B
    assert "axis:B" in node_ids
    # A 轴是 None → 跳过
    assert "axis:A" not in node_ids


def test_builder_tcm_pathway_map_aliases():
    data = {
        "aliases": {
            "autophagy": "autophagy",       # 自映射，跳过
            "autophagic": "autophagy",
            "mito": "mitochondrial",
            "": "x",                        # 空 alias，跳过
        },
        "axis_pathways": {"A": ["ampk_mtor"]},
    }
    items = build_graph_from_tcm_pathway_map(data)
    edges = [i for i in items if i[0] == "edge" and i[1][2] == "relates_to"]
    edge_pairs = {(e[1][0], e[1][1]) for e in edges}
    assert ("pathway:autophagic", "pathway:autophagy") in edge_pairs
    assert ("pathway:mito", "pathway:mitochondrial") in edge_pairs
    # 自映射被跳过
    assert ("pathway:autophagy", "pathway:autophagy") not in edge_pairs


def test_builder_tcm_pathway_map_creates_alias_nodes():
    """别名两端都应预建为 pathway 节点，避免 unknown 类型。"""
    data = {
        "aliases": {"pgc1a": "pgc1a_sirt"},
    }
    items = build_graph_from_tcm_pathway_map(data)
    nodes = [i for i in items if i[0] == "node"]
    node_ids = {n[1][0] for n in nodes}
    assert "pathway:pgc1a" in node_ids
    assert "pathway:pgc1a_sirt" in node_ids
    # 均为 pathway 类型
    for n in nodes:
        assert n[1][1] == "pathway"


# ---------------------------------------------------------------------------
# load_graph 缓存
# ---------------------------------------------------------------------------


def test_load_graph_from_cache():
    g = load_graph()
    assert g.stats()["node_count"] > 500
    assert g.stats()["edge_count"] > 500


def test_load_graph_rebuild_flag(tmp_path, monkeypatch):
    """rebuild=True 应跳过缓存，从源重建。"""
    g1 = load_graph()
    g2 = load_graph(rebuild=True)
    assert g1.stats()["node_count"] == g2.stats()["node_count"]


def test_load_graph_with_custom_cache(tmp_path, monkeypatch):
    """HL_GRAPH_CACHE 环境变量应覆盖缓存位置。"""
    custom = tmp_path / "custom_graph.json"
    monkeypatch.setenv("HL_GRAPH_CACHE", str(custom))
    # 强制重建并写回
    g = load_graph(rebuild=True)
    assert custom.exists(), "自定义缓存路径未写入"
    # 读回
    g2 = load_graph()
    assert g2.stats()["node_count"] == g.stats()["node_count"]


# ---------------------------------------------------------------------------
# fail-loud：源数据全缺
# ---------------------------------------------------------------------------


def test_build_from_sources_all_missing_raises(tmp_path, monkeypatch):
    """所有源文件缺失时 → GraphDataMissingError（fail-loud）。"""
    # 用一个不存在的路径 monkeypatch 掉 _DATA_DIR
    import app.lib.graphrag_engine as eng
    orig = eng._DATA_DIR
    monkeypatch.setattr(eng, "_DATA_DIR", tmp_path)
    try:
        with pytest.raises(GraphDataMissingError):
            eng.build_from_sources()
    finally:
        monkeypatch.setattr(eng, "_DATA_DIR", orig)


# ---------------------------------------------------------------------------
# API 端点测试
# ---------------------------------------------------------------------------


# 公共 fixture：获取真实图谱（通过 API 隐式调用 build_from_sources）
async def _get_known_herb_node_id(client):
    """通过 /search 找一个真实存在的 herb 节点 id。"""
    resp = await client.get("/api/v1/graphrag/search", params={"q": "甘草", "type": "herb"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) > 0, "测试前提：图谱中应有「甘草」"
    return results[0]["id"]


@pytest.mark.asyncio
async def test_api_stats_public(client):
    resp = await client.get("/api/v1/graphrag/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["node_count"] > 0
    assert data["edge_count"] > 0
    assert "type_distribution" in data
    assert "relation_distribution" in data
    assert "wellness_disclaimer" in data


@pytest.mark.asyncio
async def test_api_get_node_existing(client):
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.get(f"/api/v1/graphrag/nodes/{herb_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["node"]["id"] == herb_id
    assert data["node"]["type"] == "herb"


@pytest.mark.asyncio
async def test_api_get_node_not_found(client):
    resp = await client.get("/api/v1/graphrag/nodes/nonexistent_node")
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_neighbors_out_direction(client):
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.get(
        f"/api/v1/graphrag/nodes/{herb_id}/neighbors",
        params={"direction": "out"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["node_id"] == herb_id
    assert isinstance(data["neighbors"], list)


@pytest.mark.asyncio
async def test_api_neighbors_relation_filter(client):
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.get(
        f"/api/v1/graphrag/nodes/{herb_id}/neighbors",
        params={"direction": "out", "relation": "axis_of"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for nb in data["neighbors"]:
        # 邻居本身可能是 axis 类型
        assert "id" in nb


@pytest.mark.asyncio
async def test_api_neighbors_not_found(client):
    resp = await client.get("/api/v1/graphrag/nodes/nonexistent/neighbors")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_neighbors_bad_direction_422(client):
    resp = await client.get(
        "/api/v1/graphrag/nodes/x/neighbors",
        params={"direction": "sideways"},
    )
    # FastAPI pattern 校验 → 422
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_search_by_label(client):
    resp = await client.get("/api/v1/graphrag/search", params={"q": "甘草"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] > 0
    assert all("甘草" in n["label"] or "甘草" in n["id"] for n in data["results"])


@pytest.mark.asyncio
async def test_api_search_by_type(client):
    resp = await client.get("/api/v1/graphrag/search", params={"q": "axis", "type": "axis"})
    assert resp.status_code == 200
    data = resp.json()
    for n in data["results"]:
        assert n["type"] == "axis"


@pytest.mark.asyncio
async def test_api_search_bad_type_400(client):
    resp = await client.get("/api/v1/graphrag/search", params={"q": "x", "type": "not_a_type"})
    assert resp.status_code == 400
    assert "未知节点类型" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_search_empty_query_422(client):
    resp = await client.get("/api/v1/graphrag/search", params={"q": ""})
    # min_length=1 → 422
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_search_limit_client(client):
    resp = await client.get("/api/v1/graphrag/search", params={"q": "axis", "limit": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] <= 3


@pytest.mark.asyncio
async def test_api_query_requires_auth(client):
    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": "herb:x:y", "end": "axis:A"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_axis_related_requires_auth(client):
    resp = await client.get("/api/v1/graphrag/axes/A/related")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_api_herb_profile_requires_auth(client):
    resp = await client.get("/api/v1/graphrag/herb/herb%3A神农本草经%3A甘草/profile")
    assert resp.status_code in (401, 403)


async def _auth_headers(client, test_user_data):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    if reg.status_code not in (200, 201):
        pytest.skip(f"Registration failed: {reg.status_code}")
    login = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_query_path_found(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    herb_id = await _get_known_herb_node_id(client)
    # 从 herb 直接到 axis（treats 关系或 axis_of）——先随便找一个存在的 axis
    resp = await client.get("/api/v1/graphrag/search", params={"q": "axis", "type": "axis"})
    axis_nodes = resp.json()["results"]
    assert axis_nodes, "图谱中应有 axis 节点"
    axis_id = axis_nodes[0]["id"]

    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": herb_id, "end": axis_id, "max_depth": 6},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # 找到或明确告知未找到
    assert "found" in data
    if data["found"]:
        assert data["path"][0] == herb_id
        assert data["path"][-1] == axis_id
        assert len(data["nodes"]) >= 2
        assert "wellness_disclaimer" in data


@pytest.mark.asyncio
async def test_api_query_path_no_path(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    # 构造一个必定无路径的场景：start==end 之外的孤立节点
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": herb_id, "end": "definitely_no_path_node_xyz", "max_depth": 6},
        headers=headers,
    )
    # 目标节点不存在 → 404
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_query_path_bad_depth_422(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": herb_id, "end": "axis:A", "max_depth": 100},
        headers=headers,
    )
    assert resp.status_code == 422  # max_depth le=12


@pytest.mark.asyncio
async def test_api_query_path_start_missing_404(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": "no_such_node", "end": "axis:A", "max_depth": 6},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_axis_related_valid(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.get("/api/v1/graphrag/axes/A/related", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["axis_id"] == "A"
    assert "counts" in data
    assert "total" in data["counts"]
    assert "related" in data
    # 至少应有一些 herb/food/pulse 关联
    assert data["counts"]["total"] > 0


@pytest.mark.asyncio
async def test_api_axis_related_bad_axis_400(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.get("/api/v1/graphrag/axes/Z/related", headers=headers)
    assert resp.status_code == 400
    assert "未知轴" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_api_axis_related_case_insensitive(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.get("/api/v1/graphrag/axes/a/related", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["axis_id"] == "A"


@pytest.mark.asyncio
async def test_api_herb_profile_existing(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    herb_id = await _get_known_herb_node_id(client)
    # URL 编码
    from urllib.parse import quote
    encoded = quote(herb_id, safe="")
    resp = await client.get(f"/api/v1/graphrag/herb/{encoded}/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["herb"]["id"] == herb_id
    for k in ("axes", "conditions", "sources", "related_herbs"):
        assert k in data
        assert isinstance(data[k], list)


@pytest.mark.asyncio
async def test_api_herb_profile_by_label(client, test_user_data):
    """支持用 label（中文药材名）查询，而非仅节点 id。"""
    headers = await _auth_headers(client, test_user_data)
    from urllib.parse import quote
    resp = await client.get(
        f"/api/v1/graphrag/herb/{quote('甘草')}/profile",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_api_herb_profile_not_found(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.get("/api/v1/graphrag/herb/不存在的药材XXX/profile", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_all_responses_have_disclaimer(client, test_user_data):
    """所有响应带 wellness_disclaimer（wellness 边界）。"""
    headers = await _auth_headers(client, test_user_data)

    # stats
    resp = await client.get("/api/v1/graphrag/stats")
    assert "wellness_disclaimer" in resp.json()

    # search
    resp = await client.get("/api/v1/graphrag/search", params={"q": "axis"})
    assert "wellness_disclaimer" in resp.json()

    # node
    herb_id = await _get_known_herb_node_id(client)
    resp = await client.get(f"/api/v1/graphrag/nodes/{herb_id}")
    assert "wellness_disclaimer" in resp.json()

    # neighbors
    resp = await client.get(f"/api/v1/graphrag/nodes/{herb_id}/neighbors")
    assert "wellness_disclaimer" in resp.json()

    # axis related
    resp = await client.get("/api/v1/graphrag/axes/A/related", headers=headers)
    assert "wellness_disclaimer" in resp.json()

    # herb profile
    from urllib.parse import quote
    resp = await client.get(f"/api/v1/graphrag/herb/{quote('甘草')}/profile", headers=headers)
    assert "wellness_disclaimer" in resp.json()

    # query path
    resp = await client.post(
        "/api/v1/graphrag/query",
        json={"start": herb_id, "end": "axis:A", "max_depth": 6},
        headers=headers,
    )
    assert "wellness_disclaimer" in resp.json()


@pytest.mark.asyncio
async def test_api_wellness_disclaimer_no_medical_terms(client):
    """响应文案不含医疗禁区词。"""
    resp = await client.get("/api/v1/graphrag/stats")
    disclaimer = resp.json()["wellness_disclaimer"]
    for forbidden in ("诊断", "治疗", "患者", "医疗"):
        assert forbidden not in disclaimer, f"disclaimer 含禁区词: {forbidden}"
