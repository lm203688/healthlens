"""GraphRAG 图谱构建器（S2-5）

把结构化源数据（tcm_structured / classical_slices / pulse_signatures /
axis_term_mapping / tcm_pathway_map）转换为 (节点, 边) 元组列表。

约定：
- 每个函数返回 list[tuple]，元素为 ("node", (id, type, label, **props)) 或
  ("edge", (src, dst, relation, **props))。调用方（build_from_sources）负责
  分发到 KnowledgeGraph.add_node / add_edge。
- 节点 id 命名空间：
    herb:{book}:{name}     — 药材（按书名区分，避免神农本草经/食疗本草同名冲突）
    food:{book}:{name}     — 食疗法
    pulse:{id}             — 脉象
    axis:{A..H}            — 八轴
    term:{zh}              — GB/T 术语
    pathway:{name}         — 西医通路
    text:{book}:{entity}   — 古籍文本
- wellness 边界：builder 只做结构组装，不做医学判断。
"""
from __future__ import annotations

from typing import Any

NodeItem = tuple[str, tuple[Any, ...]]
EdgeItem = tuple[str, tuple[Any, ...]]
BuildItem = NodeItem | EdgeItem

# 轴 ID 白名单（八轴 A-H）
_AXIS_IDS = {"A", "B", "C", "D", "E", "F", "G", "H"}

# 轴中文标签（供节点 label 使用；缺失时兜底为 "axis:{id}"）
_AXIS_LABELS = {
    "A": "气化轴",
    "B": "气血轴",
    "C": "络脉轴",
    "D": "昼夜轴",
    "E": "脏腑轴",
    "F": "正邪轴",
    "G": "神志轴",
    "H": "肾精轴",
}


def _node(node_id: str, node_type: str, label: str, **props: Any) -> BuildItem:
    """构造节点条目（keyword-only 简化调用方）。"""
    return ("node", (node_id, node_type, label, props))


def _edge(src: str, dst: str, relation: str, **props: Any) -> BuildItem:
    """构造边条目。"""
    return ("edge", (src, dst, relation, props))


def _axis_id_of_hint(hint: str | None) -> str | None:
    """从 axis_hint（如 "F" 或 "F正邪"）提取八轴字母。"""
    if not hint:
        return None
    h = str(hint).strip()
    if h in _AXIS_IDS:
        return h
    # 兼容 "A气化" / "F 正邪" 之类的写法
    for ch in h:
        if ch in _AXIS_IDS:
            return ch
    return None


def _herb_node_id(book: str, name: str) -> str:
    return f"herb:{book}:{name}"


def _food_node_id(book: str, name: str) -> str:
    return f"food:{book}:{name}"


def _text_node_id(book: str, entity: str) -> str:
    return f"text:{book}:{entity}"


def _pulse_node_id(pid: str) -> str:
    return f"pulse:{pid}"


def _axis_node_id(axis_id: str) -> str:
    return f"axis:{axis_id}"


def _term_node_id(zh: str) -> str:
    return f"term:{zh}"


def _pathway_node_id(name: str) -> str:
    return f"pathway:{name}"


# ---------------------------------------------------------------------------
# 各源数据构建器
# ---------------------------------------------------------------------------


def build_graph_from_tcm_structured(data: dict, *, book: str | None = None) -> list[BuildItem]:
    """从 tcm_structured（神农本草经 / 食疗本草）构建节点和边。

    - type == "herb" → herb 节点
    - type == "food" / "food_therapy" / "dietary" → food 节点
    - efficacy 非空 → treats 边到 condition:{efficacy} 节点
    - source_quote 非空 → from_text 边到 text:{book}:{name} 节点
    """
    items: list[BuildItem] = []
    book_name = book or data.get("book") or "unknown"
    entities = data.get("entities") or []
    seen_condition_ids: set[str] = set()

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        name = (ent.get("name") or "").strip()
        if not name:
            continue
        etype_raw = (ent.get("type") or "").strip().lower()
        is_food = etype_raw in ("food", "food_therapy", "dietary", "foodtherapy")
        if is_food:
            node_id = _food_node_id(book_name, name)
            node_type = "food"
        else:
            node_id = _herb_node_id(book_name, name)
            node_type = "herb"

        props = {
            "name": name,
            "book": book_name,
            "property": ent.get("property") or None,
            "efficacy": ent.get("efficacy") or None,
            "evidence_level": ent.get("evidence_level") or None,
        }
        items.append(_node(node_id, node_type, name, **props))

        # treats 边：efficacy → condition 节点
        efficacy = (ent.get("efficacy") or "").strip()
        if efficacy:
            cond_id = f"condition:{efficacy}"
            if cond_id not in seen_condition_ids:
                seen_condition_ids.add(cond_id)
                items.append(_node(cond_id, "condition", efficacy))
            items.append(_edge(node_id, cond_id, "treats",
                               evidence_level=ent.get("evidence_level") or None))

        # from_text 边：source_quote → classical_text 节点
        source_quote = (ent.get("source_quote") or "").strip()
        if source_quote:
            text_id = _text_node_id(book_name, name)
            items.append(_node(
                text_id, "classical_text", f"{book_name}·{name}",
                book=book_name,
                entity=name,
                passage=source_quote[:500],  # 截断，防止缓存膨胀
                author=data.get("author"),
                dynasty=data.get("dynasty"),
            ))
            items.append(_edge(node_id, text_id, "from_text",
                               book=book_name,
                               passage_len=len(source_quote)))

    return items


def build_graph_from_classical_slices(data: dict) -> list[BuildItem]:
    """从 classical_slices 构建节点和边。

    - 每条 slice 若 entity_type 已知 → 补 axis_of 边（axis_hint / axis_hint_secondary）
    - 若 slice.passage 非空 → 更新对应 text 节点（book+entity 唯一）
    """
    items: list[BuildItem] = []
    slices = data.get("slices") or []
    seen_text_ids: set[str] = set()
    seen_edge_keys: set[tuple[str, str, str]] = set()

    for sl in slices:
        if not isinstance(sl, dict):
            continue
        book = (sl.get("book") or "").strip()
        entity = (sl.get("entity") or "").strip()
        if not book or not entity:
            continue

        entity_type_raw = (sl.get("entity_type") or "herb").strip().lower()
        is_food = entity_type_raw in ("food", "food_therapy", "dietary")
        node_type = "food" if is_food else "herb"
        node_id = (_food_node_id if is_food else _herb_node_id)(book, entity)

        # 补充 entity 节点（若 tcm_structured 未含，此处保底创建）
        items.append(_node(
            node_id, node_type, entity,
            book=book,
            property=sl.get("property"),
            efficacy=sl.get("efficacy"),
            evidence_level=sl.get("evidence_level"),
        ))

        # from_text 边
        passage = (sl.get("passage") or "").strip()
        if passage:
            text_id = _text_node_id(book, entity)
            if text_id not in seen_text_ids:
                seen_text_ids.add(text_id)
                items.append(_node(
                    text_id, "classical_text", f"{book}·{entity}",
                    book=book,
                    entity=entity,
                    passage=passage[:500],
                    author=sl.get("author"),
                    dynasty=sl.get("dynasty"),
                ))
            key = (node_id, text_id, "from_text")
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                items.append(_edge(node_id, text_id, "from_text",
                                   book=book,
                                   slice_id=sl.get("slice_id"),
                                   axis_confidence=sl.get("axis_confidence"),
                                   needs_expert_review=sl.get("needs_expert_review", True),
                                   ))

        # axis_of 边（axis_hint / axis_hint_secondary）
        primary = _axis_id_of_hint(sl.get("axis_hint"))
        secondary = _axis_id_of_hint(sl.get("axis_hint_secondary"))
        confidence = sl.get("axis_confidence") or None
        for axis_id, primary_flag in [(primary, True), (secondary, False)]:
            if not axis_id:
                continue
            axis_node = _axis_node_id(axis_id)
            items.append(_node(axis_node, "axis", _AXIS_LABELS.get(axis_id, axis_id),
                               axis_id=axis_id,
                               axis_label=sl.get("axis_label") if primary_flag else None))
            key = (node_id, axis_node, "axis_of")
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                items.append(_edge(node_id, axis_node, "axis_of",
                                   confidence=confidence,
                                   primary=primary_flag,
                                   axis_method=sl.get("axis_method"),
                                   needs_expert_review=sl.get("needs_expert_review", True),
                                   ))

    return items


def build_graph_from_pulse_signatures(data: dict) -> list[BuildItem]:
    """从 pulse_signatures 构建脉象节点 + axis_of 边。"""
    items: list[BuildItem] = []
    pulses = data.get("pulses") or []
    seen_edge_keys: set[tuple[str, str, str]] = set()

    for p in pulses:
        if not isinstance(p, dict):
            continue
        pid = (p.get("id") or "").strip()
        if not pid:
            continue
        name = (p.get("name") or pid).strip()
        node_id = _pulse_node_id(pid)
        items.append(_node(
            node_id, "pulse", name,
            id=pid,
            pinyin=p.get("pinyin"),
            category=p.get("category"),
            definition=p.get("definition"),
            wellness_ref=p.get("wellness_ref"),
            guardrail=p.get("guardrail"),
            tags=p.get("tags"),
        ))
        # axes 字段：字符串形如 "A气化" → 取首字母
        for ax_raw in (p.get("axes") or []):
            axis_id = _axis_id_of_hint(str(ax_raw))
            if not axis_id:
                continue
            axis_node = _axis_node_id(axis_id)
            items.append(_node(axis_node, "axis", _AXIS_LABELS.get(axis_id, axis_id),
                               axis_id=axis_id))
            key = (node_id, axis_node, "axis_of")
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                items.append(_edge(node_id, axis_node, "axis_of",
                                   label=str(ax_raw), source="pulse_signatures"))

    return items


def build_graph_from_axis_term_mapping(data: dict) -> list[BuildItem]:
    """从 axis_term_mapping 构建 axis / term / pathway 节点及 maps_to 边。"""
    items: list[BuildItem] = []
    axes = data.get("axes") or {}
    for axis_id, ax in axes.items():
        if not isinstance(ax, dict):
            continue
        axis_node = _axis_node_id(axis_id)
        axis_label = ax.get("axis_label") or _AXIS_LABELS.get(axis_id, axis_id)
        items.append(_node(
            axis_node, "axis", axis_label,
            axis_id=axis_id,
            source="axis_term_mapping",
        ))

        # GB/T 术语节点 + maps_to 边
        gbt = ax.get("gbt_20348_2026") or {}
        zh = (gbt.get("zh") or "").strip()
        if zh:
            term_id = _term_node_id(zh)
            items.append(_node(
                term_id, "term", zh,
                zh=zh,
                en=gbt.get("en"),
                note=gbt.get("note"),
                gbt_confirmation_required=gbt.get("gbt_confirmation_required"),
            ))
            items.append(_edge(term_id, axis_node, "maps_to",
                               standard="GB/T 20348-2026",
                               axis_id=axis_id,
                               ))

        # 通路节点 + maps_to 边
        for pw in (ax.get("pathways") or []):
            pw_str = str(pw).strip()
            if not pw_str:
                continue
            pw_node = _pathway_node_id(pw_str)
            items.append(_node(pw_node, "pathway", pw_str, source="axis_term_mapping"))
            items.append(_edge(term_id if zh else axis_node, pw_node, "maps_to",
                               axis_id=axis_id, kind="pathway"))

        # classical_books → 关联 classical_text 占位节点（book 级）
        for book in (ax.get("classical_books") or []):
            book_str = str(book).strip()
            if not book_str:
                continue
            book_node = f"text:{book_str}"
            items.append(_node(book_node, "classical_text", book_str, book=book_str))
            items.append(_edge(book_node, axis_node, "axis_of",
                               confidence=None, primary=False,
                               kind="classical_book", source="axis_term_mapping"))

    return items


def build_graph_from_tcm_pathway_map(data: dict) -> list[BuildItem]:
    """从 tcm_pathway_map 补充 pathway 节点 + 别名 relates_to 边。

    - axis_labels / axis_pathways：与 axis_term_mapping 语义一致，此处只补
      axis_term_mapping 未覆盖的通路（如 alias 名）
    - aliases：把别名作为 pathway 节点，用 relates_to 边指向规范通路
    """
    items: list[BuildItem] = []
    # 别名 → 规范通路（relates_to）
    aliases = data.get("aliases") or {}
    for alias, canonical in aliases.items():
        a = str(alias).strip()
        c = str(canonical).strip()
        if not a or not c or a == c:
            continue
        a_node = _pathway_node_id(a)
        c_node = _pathway_node_id(c)
        # 别名与规范通路都是通路节点（避免 add_edge 兜底成 unknown）
        items.append(_node(a_node, "pathway", a, source="tcm_pathway_map_alias",
                           alias_of=c))
        items.append(_node(c_node, "pathway", c, source="tcm_pathway_map"))
        items.append(_edge(a_node, c_node, "relates_to", kind="pathway_alias",
                           alias_of=c))

    # 若 alias 表未覆盖某通路，仍补建节点（保证图谱可查）
    for axis_id, pws in (data.get("axis_pathways") or {}).items():
        for pw in (pws or []):
            pw_str = str(pw).strip()
            if not pw_str:
                continue
            pw_node = _pathway_node_id(pw_str)
            items.append(_node(pw_node, "pathway", pw_str,
                               axis_id=str(axis_id), source="tcm_pathway_map"))

    return items


# ---------------------------------------------------------------------------
# 全量构建
# ---------------------------------------------------------------------------


def full_build(save: bool = True) -> "KnowledgeGraph":
    """全量构建图谱（调用 build_from_sources 并可选写盘）。

    与 build_from_sources 的区别：full_build 会确保缓存目录存在，并把
    生成的图谱写回 data/graphrag/knowledge_graph.json。
    """
    from app.lib.graphrag_engine import (
        _GRAPH_CACHE_FILE,
        GraphDataMissingError,
        build_from_sources,
    )

    try:
        graph = build_from_sources()
    except GraphDataMissingError:
        # fail-loud：源数据全缺 → 直接向调用方抛错
        raise

    if save:
        _GRAPH_CACHE_DIR = _GRAPH_CACHE_FILE.parent
        _GRAPH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _GRAPH_CACHE_FILE.write_text(
            json_dumps(graph.serialize()),
            encoding="utf-8",
        )
    return graph


def json_dumps(obj) -> str:
    """小工具：统一 JSON 序列化策略（utf-8, 缩进 2, ensure_ascii=False）。"""
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
