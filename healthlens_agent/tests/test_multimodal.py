"""多模态八轴倾向原型测试。"""

from healthlens_agent.multimodal import analyze, tool_face_color, tool_tongue_color


def test_analyze_returns_report():
    rep = analyze("舌淡红、苔薄白、面色萎黄、体态乏力")
    assert rep.dominant_axis.startswith("B")  # 气血-线粒体
    assert rep.safety_passed is True
    assert 0.0 < rep.axis_probs[rep.dominant_axis] <= 1.0


def test_tool_tongue_color():
    r = tool_tongue_color("舌淡红")
    assert r.confidence > 0
    assert r.finding == "淡红"


def test_tool_face_color_unknown():
    r = tool_face_color("正常面色")
    # 不匹配任何规则时 confidence=0（被 analyze 过滤）
    assert r.confidence == 0.0


def test_analyze_blocks_emergency_text():
    rep = analyze("我胸痛伴随呼吸困难")
    assert rep.safety_passed is False
