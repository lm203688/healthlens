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
