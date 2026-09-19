"""八轴融合引擎 × 轴间桥接网络（含 A↔F 焦亡抑制）回归测试

验证：gasdermin/焦亡范式借鉴落地为可呈现的机制链条。
确定性、零外部依赖（与 test_fusion_engine_bioage.py 同构）。
"""

from app.lib.fusion_engine import (
    AXIS_BRIDGES,
    axis_bridges_for,
)


def test_bridges_constant_present():
    assert isinstance(AXIS_BRIDGES, list)
    assert len(AXIS_BRIDGES) >= 1


def test_pyroptosis_bridge_present_and_well_formed():
    """头条条目：A(自噬)→F(正邪-炎症) 焦亡抑制，机制锚点含 GSDMD/NLRP3。"""
    keys = {(b["from"], b["to"]) for b in AXIS_BRIDGES}
    assert ("A", "F") in keys

    a2f = next(b for b in AXIS_BRIDGES if (b["from"], b["to"]) == ("A", "F"))
    assert "GSDMD" in a2f["molecules"]
    assert "NLRP3" in a2f["molecules"]
    assert "caspase-1" in a2f["molecules"]
    assert a2f["direction"] == "negative"          # 自噬↑ → 焦亡性炎症↓
    assert a2f["hypothesis_level"] is True         # 假说级、非临床
    assert "选择性降解" in a2f["mechanism"]          # 自噬-溶酶体降解炎症小体


def test_bridges_f_when_weak_F():
    """弱项含 F → 返回 A→F 桥接，供前端解释『炎症轴偏弱的机制根因』。"""
    bridges = axis_bridges_for({"F"})
    assert any((b["from"], b["to"]) == ("A", "F") for b in bridges)


def test_bridges_f_when_weak_A():
    """弱项含 A → 同样返回 A→F（自噬是干预抓手，可降焦亡性炎症）。"""
    bridges = axis_bridges_for({"A"})
    assert any((b["from"], b["to"]) == ("A", "F") for b in bridges)


def test_bridges_multiple_axes():
    """弱项含 A 与 F → 返回 A→F（去重，非重复两条）。"""
    bridges = axis_bridges_for({"A", "F"})
    a2f = [b for b in bridges if (b["from"], b["to"]) == ("A", "F")]
    assert len(a2f) == 1


def test_bridges_unrelated_axis_empty():
    """未定义桥接的轴（如 C 脏腑）→ 返回空，不臆造机制。"""
    assert axis_bridges_for({"C"}) == []


# ---------------------------------------------------------------------------
# v0.6 增补（2026-09-19）：H（先天-肾精）作为上游枢纽的两条出边
# 锚点来自前沿机制（RNA 剪接体稳态 / OSK 部分重编程），均为 Tier-3 假说级。
# 这两条的特殊约束是「不得被读成干预承诺」，因此额外断言 intervention_link
# 里写明了不涉及靶向干预。
# ---------------------------------------------------------------------------


def test_h_out_edges_present():
    """H 应有两条出边：H→F（剪接稳态→炎症）与 H→A（表观遗传→自噬转录）。"""
    keys = {(b["from"], b["to"]) for b in AXIS_BRIDGES}
    assert ("H", "F") in keys
    assert ("H", "A") in keys


def test_h_to_f_splicing_bridge_well_formed():
    """H→F：剪接失调 → 异常蛋白亚型与炎症负荷，方向为负（H 强则炎症低）。"""
    h2f = next(b for b in AXIS_BRIDGES if (b["from"], b["to"]) == ("H", "F"))
    assert h2f["direction"] == "negative"
    assert h2f["hypothesis_level"] is True
    assert "剪接" in h2f["mechanism"]
    for mol in ("SF3B1", "U2AF2", "IL-6"):
        assert mol in h2f["molecules"]
    # 该锚点是疾病靶点研究，不是健康管理手段
    assert "不涉及任何剪接靶向药物" in h2f["intervention_link"]


def test_h_to_a_reprogramming_bridge_well_formed():
    """H→A：表观遗传完整性/部分重编程 → 自噬相关基因转录程序，方向为正。"""
    h2a = next(b for b in AXIS_BRIDGES if (b["from"], b["to"]) == ("H", "A"))
    assert h2a["direction"] == "positive"
    assert h2a["hypothesis_level"] is True
    for mol in ("Oct4", "Sox2", "Klf4"):
        assert mol in h2a["molecules"]
    # 红线：不得据此声称任何重编程干预
    assert "不涉及任何重编程干预" in h2a["intervention_link"]


def test_new_bridges_are_tier3_hypothesis_only():
    """新增两条必须是假说级且标注 Tier-3，避免被当成已验证结论。"""
    for pair in (("H", "F"), ("H", "A")):
        b = next(x for x in AXIS_BRIDGES if (x["from"], x["to"]) == pair)
        assert b["hypothesis_level"] is True
        assert "Tier-3" in b["evidence"]


def test_bridges_returned_when_H_weak():
    """弱项含 H → 返回 H 的三条相关边（含 H→F、H→A），供前端解释先天轴根因。"""
    bridges = axis_bridges_for({"H"})
    pairs = {(b["from"], b["to"]) for b in bridges}
    assert ("H", "F") in pairs
    assert ("H", "A") in pairs


def test_all_bridge_pairs_unique():
    """同一 (from, to) 不得重复定义，否则前端会渲染重复机制卡片。"""
    pairs = [(b["from"], b["to"]) for b in AXIS_BRIDGES]
    assert len(pairs) == len(set(pairs))


def test_all_bridges_have_required_fields():
    """字段完整性：缺 molecules / evidence / intervention_link 会让前端渲染残缺。"""
    for b in AXIS_BRIDGES:
        for field in ("from", "to", "direction", "mechanism",
                      "molecules", "evidence", "hypothesis_level",
                      "intervention_link"):
            assert field in b, f"{b.get('from')}->{b.get('to')} 缺字段 {field}"
        assert b["molecules"], f"{b['from']}->{b['to']} molecules 为空"
        assert not b["from"] == b["to"], "不允许自环桥接"
