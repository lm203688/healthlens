"""脉象解读引擎 + 号脉连接器自测（纯函数，不起 app）"""
from app.connectors import pulse_gateway
from app.lib import pulse_engine


def _feat(overrides=None):
    base = {
        "hl.pulse.rate_bpm": 72,
        "hl.pulse.h1": 0.6,
        "hl.pulse.h3_h1": 0.6,
        "hl.pulse.h4_h1": 0.5,
        "hl.pulse.h5_h1": 0.4,
        "hl.pulse.dicrotic_present": 1,
        "hl.pulse.ascending_slope": 0.5,
        "hl.pulse.perfusion_index": 0.6,
        "hl.pulse.rhythm_regularity": 1.0,
        "hl.pulse.pause_pattern": "none",
        "hl.pulse.depth": "",
    }
    if overrides:
        base.update(overrides)
    return base


def _ids(features):
    return {lab["id"] for lab in pulse_engine.classify_pulse(features)["labels"]}


def test_shu_num_pulse():
    ids = _ids(_feat({"hl.pulse.rate_bpm": 96}))
    assert "shu" in ids


def test_chi_slow_pulse():
    ids = _ids(_feat({"hl.pulse.rate_bpm": 54}))
    assert "chi" in ids


def test_ji_critical_pulse():
    r = pulse_engine.classify_pulse(_feat({"hl.pulse.rate_bpm": 112}))
    assert "ji" in {lab["id"] for lab in r["labels"]}
    assert r["severity"] == "alert"


def test_xian_wiry_pulse():
    ids = _ids(_feat({"hl.pulse.h3_h1": 0.9}))
    assert "xian" in ids


def test_hua_slippery_pulse():
    ids = _ids(_feat({"hl.pulse.dicrotic_present": 1, "hl.pulse.h1": 0.78}))
    assert "hua" in ids


def test_se_choppy_pulse():
    ids = _ids(_feat({"hl.pulse.dicrotic_present": 0}))
    assert "se" in ids


def test_hong_surging_pulse():
    ids = _ids(_feat({"hl.pulse.h1": 0.9, "hl.pulse.h3_h1": 0.3}))
    assert "hong" in ids


def test_jie_knotted_pulse():
    ids = _ids(_feat({"hl.pulse.rate_bpm": 55, "hl.pulse.pause_pattern": "irregular"}))
    assert "jie" in ids


def test_dai_intermittent_pulse():
    r = pulse_engine.classify_pulse(_feat({"hl.pulse.pause_pattern": "regular"}))
    assert "dai" in {lab["id"] for lab in r["labels"]}
    assert r["severity"] == "alert"


def test_fu_superficial_depth():
    ids = _ids(_feat({"hl.pulse.depth": "superficial"}))
    assert "fu" in ids


def test_chen_deep_depth():
    ids = _ids(_feat({"hl.pulse.depth": "deep"}))
    assert "chen" in ids


def test_ping_normal_pulse_no_label():
    r = pulse_engine.classify_pulse(_feat())
    assert r["labels"] == []
    assert r["severity"] == "normal"


def test_axis_signals_mapped():
    r = pulse_engine.classify_pulse(_feat({"hl.pulse.h3_h1": 0.9}))
    # 弦脉应映射到 A/C 等八轴之一
    assert isinstance(r["axis_signals"], dict)
    assert len(r["axis_signals"]) > 0


def test_guardrail_present_always():
    r = pulse_engine.classify_pulse(_feat())
    assert "guardrail" in r and r["guardrail"]


def test_connector_interpret_payloads():
    payloads = [{
        "day": "2026-10-05",
        "user_ref": "u1",
        "metrics": [
            {"key": "hl.pulse.rate_bpm", "value": 96},
            {"key": "hl.pulse.h3_h1", "value": 0.9},
            {"key": "hl.pulse.h1", "value": 0.6},
            {"key": "hl.pulse.dicrotic_present", "value": 1},
            {"key": "hl.pulse.ascending_slope", "value": 0.5},
            {"key": "hl.pulse.rhythm_regularity", "value": 1.0},
            {"key": "hl.pulse.pause_pattern", "value": "none"},
        ],
    }]
    out = pulse_gateway.interpret_payloads(payloads, "u1")
    assert out["available"] is True
    assert "shu" in out["pulse_interpretation"]["labels"][0]["id"] or out["pulse_interpretation"]["labels"]
    assert out["items"][0]["source"].startswith("pulse_gateway:")


def test_connector_no_pulse_data():
    out = pulse_gateway.interpret_payloads([{"day": "2026-10-05", "metrics": [{"key": "heart_rate", "value": 70}]}], "u2")
    assert out["available"] is False
    assert out["pulse_interpretation"] is None


# ============ 相兼脉合成（2026-10-05 补）============

def test_compound_composed_when_two_pulses_hit():
    """弦(h3/h1 高) + 滑(h1 高且切迹清晰) → 应合成相兼脉。"""
    out = pulse_engine.classify_pulse(_feat({
        "hl.pulse.rate_bpm": 95,        # → 数(shu)
        "hl.pulse.h1": 0.85,            # → 洪(hong)
        "hl.pulse.h3_h1": 0.85,         # → 弦(xian)
        "hl.pulse.dicrotic_present": 1,
    }))
    names = {c["name"] for c in out["compounds"]}
    assert names, f"应至少合成一个相兼脉，实际 labels={[lab['id'] for lab in out['labels']]}"
    # 每个相兼脉的 compose 长度必须 >= 2，且置信不高于其组成单脉
    for c in out["compounds"]:
        assert len(c["compose"]) >= 2
        assert 0 < c["confidence"] <= 1.0
        assert c["ref"], "相兼脉应带传统参考"


def test_compound_confidence_not_exceed_members():
    out = pulse_engine.classify_pulse(_feat({
        "hl.pulse.rate_bpm": 96,
        "hl.pulse.h1": 0.85,
        "hl.pulse.h3_h1": 0.85,
    }))
    conf = {lab["id"]: lab["confidence"] for lab in out["labels"]}
    for c in out["compounds"]:
        for pid in c["compose"]:
            assert c["confidence"] <= conf[pid] + 1e-9, "组合置信不得高于成员"


def test_single_pulse_yields_no_compound():
    out = pulse_engine.classify_pulse(_feat({"hl.pulse.rate_bpm": 96}))
    assert out["compounds"] == [], "只命中一个脉不应凭空合成"


def test_compound_wellness_ref_mentioned():
    out = pulse_engine.classify_pulse(_feat({
        "hl.pulse.rate_bpm": 96, "hl.pulse.h1": 0.85, "hl.pulse.h3_h1": 0.85,
    }))
    if out["compounds"]:
        assert "相兼" in out["wellness_ref"], "相兼脉应出现在养生参考里"


# ============ 知识库可用性守卫 ============

def test_db_available_true_in_normal_env():
    assert pulse_engine.DB_AVAILABLE is True


def test_unavailable_db_raises_instead_of_fake_result(monkeypatch):
    """知识库缺失时必须抛错，不能返回标签名退化、八轴全空的假解读。"""
    monkeypatch.setattr(pulse_engine, "DB_AVAILABLE", False)
    try:
        pulse_engine.classify_pulse(_feat())
    except pulse_engine.PulseKnowledgeBaseError as exc:
        assert "知识库" in str(exc)
    else:
        raise AssertionError("知识库不可用时不应产出解读结果")


def test_result_reports_db_available_flag():
    assert pulse_engine.classify_pulse(_feat())["db_available"] is True


def test_se_pulse_from_low_dicrotic_notch_ratio():
    """h4/h1 明显偏低是涩脉的独立证据（血管壁弹性差），不能被读成死变量。"""
    ids = _ids(_feat({
        "hl.pulse.h1": 0.6,
        "hl.pulse.dicrotic_present": 1,     # 切迹「有」但浅
        "hl.pulse.h5_h1": 0.4,              # h5 不低，故前两条都不触发
        "hl.pulse.h3_h1": 0.5,              # 不触发弦，也不触发滑
        "hl.pulse.h4_h1": 0.25,             # 切迹比很低 → 涩
    }))
    assert "se" in ids, f"低重搏切迹比应判涩脉，实际 {ids}"


def test_h4_h1_feature_is_actually_consumed():
    """回归守卫：h4_h1 若哪天又被改成死代码，此测试会失败。"""
    a = _ids(_feat({"hl.pulse.h4_h1": 0.5, "hl.pulse.dicrotic_present": 1,
                    "hl.pulse.h5_h1": 0.4, "hl.pulse.h1": 0.6, "hl.pulse.h3_h1": 0.5}))
    b = _ids(_feat({"hl.pulse.h4_h1": 0.2, "hl.pulse.dicrotic_present": 1,
                    "hl.pulse.h5_h1": 0.4, "hl.pulse.h1": 0.6, "hl.pulse.h3_h1": 0.5}))
    assert a != b, "改变 h4_h1 应当改变判定结果"
