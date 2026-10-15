"""S1-3 Pulse Gate 测试：脉象解读引擎。

覆盖知识库加载、频率/波形/深度/节律纲判定、严重度、相兼脉合成、
八轴信号、养生参考/护栏、build_pulse_observation、边界值/fail-loud。

断言实测行为（先跑后写），不断言期望行为。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# 项目根
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DB_FILE = DATA_DIR / "pulse_signatures.json"

# 导入被测模块
from app.lib import pulse_engine
from app.lib.pulse_engine import (
    PulseKnowledgeBaseError,
    _candidate_db_paths,
    _load_db,
    classify_pulse,
    build_pulse_observation,
)

# —— fixtures ——


@pytest.fixture(autouse=True)
def _reset_pulse_engine(monkeypatch):
    """每个测试重置 pulse_engine 模块状态，避免测试间污染。

    pulse_engine 在 import 时加载 _DB 和 DB_AVAILABLE，
    测试通过 monkeypatch 控制 DB_AVAILABLE 和 _DB。
    """
    # 确保测试开始时 DB_AVAILABLE 为真实加载结果
    original_db = _load_db()
    monkeypatch.setattr(pulse_engine, "_DB", original_db)
    monkeypatch.setattr(pulse_engine, "DB_AVAILABLE", bool(original_db.get("pulses")))
    yield
    # 清理


def _feats(**overrides) -> dict:
    """构造默认 pulse 特征集，允许覆盖。

    覆盖值通过关键字传入，key 用双下划线 `__` 代替点号 `.`，
    例如 `hl__pulse__rate_bpm=105` → `hl.pulse.rate_bpm: 105`。

    默认值：正常范围，不应触发任何脉象判定。
    """
    base = {
        "hl.pulse.rate_bpm": 75,
        "hl.pulse.h1": 0.5,
        "hl.pulse.h3_h1": 0.3,
        "hl.pulse.h4_h1": 0.5,
        "hl.pulse.h5_h1": 0.4,
        "hl.pulse.dicrotic_present": 0.6,
        "hl.pulse.ascending_slope": 0.5,
        "hl.pulse.perfusion_index": 0.8,
        "hl.pulse.rhythm_regularity": 0.95,
        "hl.pulse.pause_pattern": "none",
        "hl.pulse.depth": "",
    }
    for k, v in overrides.items():
        base[k.replace("__", ".")] = v
    return base


def _labels(result: dict) -> list[str]:
    """提取结果中的脉象 id 列表。"""
    return [lab["id"] for lab in result["labels"]]


def _has(result: dict, pid: str) -> bool:
    """判断结果中是否包含指定脉象 id。"""
    return pid in _labels(result)


# —— A. 知识库加载（5 用例） ——


def test_load_db_success(monkeypatch):
    """正常加载知识库，DB_AVAILABLE=True。"""
    db = _load_db()
    assert isinstance(db, dict)
    assert len(db.get("pulses", [])) >= 28
    assert bool(db.get("pulses"))  # DB_AVAILABLE 应基于此


def test_load_db_missing_file(monkeypatch, tmp_path):
    """文件不存在时返回空 dict，DB_AVAILABLE=False。"""
    # 模拟所有候选路径都不存在
    monkeypatch.setenv("HL_PULSE_DB", str(tmp_path / "nonexistent.json"))
    monkeypatch.setattr(pulse_engine, "_candidate_db_paths", lambda: [Path(tmp_path / "nonexistent.json")])
    db = _load_db()
    assert db == {}


def test_load_db_corrupt_json(monkeypatch, tmp_path):
    """JSON 解析失败时返回空 dict。"""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid json}", encoding="utf-8")
    monkeypatch.setenv("HL_PULSE_DB", str(bad_file))
    monkeypatch.setattr(pulse_engine, "_candidate_db_paths", lambda: [bad_file])
    db = _load_db()
    assert db == {}


def test_load_db_empty_pulses(monkeypatch, tmp_path):
    """pulses 字段为空时 DB_AVAILABLE=False。"""
    empty_db = {"pulses": [], "compound_examples": []}
    db_file = tmp_path / "empty.json"
    db_file.write_text(json.dumps(empty_db), encoding="utf-8")
    monkeypatch.setenv("HL_PULSE_DB", str(db_file))
    monkeypatch.setattr(pulse_engine, "_candidate_db_paths", lambda: [db_file])
    db = _load_db()
    # 空 pulses 应该被拒绝（不返回空库假结论）
    assert db == {}


def test_candidate_paths_order(monkeypatch, tmp_path):
    """路径探测顺序：HL_PULSE_DB > repo > CWD > /app/data。"""
    custom_path = tmp_path / "custom.json"
    monkeypatch.setenv("HL_PULSE_DB", str(custom_path))
    paths = _candidate_db_paths()
    # 第一个应该是 HL_PULSE_DB
    assert paths[0] == custom_path
    # 应该有 4 个候选路径（env + repo + cwd + /app/data）
    assert len(paths) >= 4
    # 最后一个是 /app/data/pulse_signatures.json（Windows 用反斜杠）
    last = str(paths[-1]).replace("\\", "/")
    assert last.startswith("/app/data/"), f"最后一个路径应为 /app/data/*: {last}"


# —— B. 频率纲判定（5 用例） ——


def test_pulse_rate_normal():
    """rate=75 → 无频率纲判定（正常范围）。"""
    result = classify_pulse(_feats(hl__pulse__rate_bpm=75))
    # 75 在 70-90 之间，不触发任何频率纲
    for pid in ("ji", "shu", "chi", "huan"):
        assert not _has(result, pid), f"不应触发 {pid}"


def test_pulse_rate_fast():
    """rate=105 → 加"急"(ji)。"""
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105))
    assert _has(result, "ji")


def test_pulse_rate_slow():
    """rate=55 → 加"迟"(chi)。"""
    result = classify_pulse(_feats(hl__pulse__rate_bpm=55))
    assert _has(result, "chi")


def test_pulse_rate_boundary_60():
    """rate=60 → 加"缓"(huan)。

    rate=60 不 < 60，所以不命中 chi；60 < 70，命中 huan。
    """
    result = classify_pulse(_feats(hl__pulse__rate_bpm=60))
    assert _has(result, "huan")
    assert not _has(result, "chi")


def test_pulse_rate_boundary_100():
    """rate=100 → 加"数"(shu)。

    rate=100 不 > 100，所以不命中 ji；100 > 90，命中 shu。
    """
    result = classify_pulse(_feats(hl__pulse__rate_bpm=100))
    assert _has(result, "shu")
    assert not _has(result, "ji")


# —— C. 波形纲判定（8 用例） ——


def test_pulse_waform_great():
    """h1=0.9 → 加"洪"(hong)。"""
    result = classify_pulse(_feats(hl__pulse__h1=0.9))
    assert _has(result, "hong")


def test_pulse_waform_weak():
    """h1=0.1 → 加"微"(wei)。"""
    result = classify_pulse(_feats(hl__pulse__h1=0.1))
    assert _has(result, "wei")


def test_pulse_waform_thin():
    """h1=0.3 → 加"细"(xi)。"""
    result = classify_pulse(_feats(hl__pulse__h1=0.3))
    assert _has(result, "xi")


def test_pulse_waform_taut():
    """h3_h1=0.9 → 加"弦"(xian)。"""
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9))
    assert _has(result, "xian")


def test_pulse_waform_smooth():
    """dicrotic=0.6, h1=0.8 → 加"滑"(hua)。"""
    result = classify_pulse(_feats(hl__pulse__dicrotic_present=0.6, hl__pulse__h1=0.8))
    assert _has(result, "hua")


def test_pulse_waform_rough():
    """dicrotic=0.2 → 加"涩"(se)。"""
    result = classify_pulse(_feats(hl__pulse__dicrotic_present=0.2))
    assert _has(result, "se")


def test_pulse_waform_rushing():
    """slope=0.8, h1=0.7 → 加"实"(shi)。"""
    result = classify_pulse(_feats(hl__pulse__ascending_slope=0.8, hl__pulse__h1=0.7))
    assert _has(result, "shi")


def test_pulse_waform_empty():
    """slope=0.2, h1=0.4 → 加"虚"(xu)。"""
    result = classify_pulse(_feats(hl__pulse__ascending_slope=0.2, hl__pulse__h1=0.4))
    assert _has(result, "xu")


# —— D. 深度纲判定（4 用例） ——


def test_pulse_depth_superficial():
    """depth="superficial" → 加"浮"(fu)。"""
    result = classify_pulse(_feats(hl__pulse__depth="superficial"))
    assert _has(result, "fu")


def test_pulse_depth_deep():
    """depth="deep" → 加"沉"(chen)。"""
    result = classify_pulse(_feats(hl__pulse__depth="deep"))
    assert _has(result, "chen")


def test_pulse_depth_by_perf():
    """perf=0.2, no depth → 加"沉"(chen) confidence=0.4。"""
    result = classify_pulse(_feats(hl__pulse__perfusion_index=0.2, hl__pulse__depth=""))
    chen_labels = [lab for lab in result["labels"] if lab["id"] == "chen"]
    assert chen_labels, "应有 chen"
    assert abs(chen_labels[0]["confidence"] - 0.4) < 0.01


def test_pulse_depth_with_weak():
    """h1=0.3, depth="deep" → 加"细"(xi) + "弱"(ruo)。"""
    result = classify_pulse(_feats(hl__pulse__h1=0.3, hl__pulse__depth="deep"))
    assert _has(result, "xi")
    assert _has(result, "ruo")


# —— E. 节律纲判定（5 用例） ——


def test_pulse_rhythm_irregular_fast():
    """pause="irregular", rate=95 → 加"促"(cu)。"""
    result = classify_pulse(_feats(hl__pulse__pause_pattern="irregular", hl__pulse__rate_bpm=95))
    assert _has(result, "cu")


def test_pulse_rhythm_irregular_slow():
    """pause="irregular", rate=55 → 加"结"(jie)。"""
    result = classify_pulse(_feats(hl__pulse__pause_pattern="irregular", hl__pulse__rate_bpm=55))
    assert _has(result, "jie")


def test_pulse_rhythm_irregular_normal():
    """pause="irregular", rate=75 → 加"结"(jie) confidence=0.5。"""
    result = classify_pulse(_feats(hl__pulse__pause_pattern="irregular", hl__pulse__rate_bpm=75))
    jie_labels = [lab for lab in result["labels"] if lab["id"] == "jie"]
    assert jie_labels, "应有 jie"
    assert abs(jie_labels[0]["confidence"] - 0.5) < 0.01


def test_pulse_rhythm_regular_pause():
    """pause="regular" → 加"代"(dai)。"""
    result = classify_pulse(_feats(hl__pulse__pause_pattern="regular"))
    assert _has(result, "dai")


def test_pulse_rhythm_low_regularity():
    """rhythm=0.5 → 加"结"(jie) confidence=0.4。"""
    result = classify_pulse(_feats(hl__pulse__rhythm_regularity=0.5, hl__pulse__pause_pattern="none"))
    jie_labels = [lab for lab in result["labels"] if lab["id"] == "jie"]
    assert jie_labels, "应有 jie"
    assert abs(jie_labels[0]["confidence"] - 0.4) < 0.01


# —— F. 严重度判定（5 用例） ——


def test_severity_normal():
    """无异常脉 → severity="normal"。"""
    result = classify_pulse(_feats())
    assert result["severity"] == "normal"


def test_severity_alert():
    """有急脉 → severity="alert"。"""
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105))
    assert result["severity"] == "alert"


def test_severity_watch():
    """有弦脉 → severity="watch"。"""
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9))
    assert result["severity"] == "watch"


def test_severity_priority():
    """同时有 alert 和 watch 脉 → severity="alert"（优先级）。"""
    # ji (alert) + xian (watch)
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105, hl__pulse__h3_h1=0.9))
    assert _has(result, "ji")
    assert _has(result, "xian")
    assert result["severity"] == "alert"


def test_severity_multiple_alerts():
    """多个 alert 脉 → severity="alert"。"""
    # ji (alert, rate>100) + wei (alert, h1<0.2)
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105, hl__pulse__h1=0.1))
    assert _has(result, "ji")
    assert _has(result, "wei")
    assert result["severity"] == "alert"


# —— G. 相兼脉合成（4 用例） ——


def test_compound_pulse_xianhua():
    """弦+数 → 合成"弦数"相兼脉。"""
    # xian (h3_h1>=0.8) + shu (rate>90)
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9, hl__pulse__rate_bpm=95))
    compound_names = [cp["name"] for cp in result["compounds"]]
    assert "弦数" in compound_names, f"应有弦数相兼脉，实际: {compound_names}"


def test_compound_pulse_confidence_discount():
    """相兼脉 confidence = min(两脉) * 0.9。"""
    # xian (0.8) + shu (0.85) → min=0.8 → 0.8*0.9=0.72
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9, hl__pulse__rate_bpm=95))
    xian_shu = [cp for cp in result["compounds"] if cp["name"] == "弦数"]
    assert xian_shu, "应有弦数相兼脉"
    # 允许 ±0.02 的舍入误差
    assert abs(xian_shu[0]["confidence"] - 0.72) < 0.03


def test_compound_pulse_max_three():
    """多组合时最多返回 3 个相兼脉。"""
    # 构造多个可能组合：xian+shu, xi+se, hu+shu
    # 但实际触发需要更多特征，简化测试：只断言不超过 3 个
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9, hl__pulse__rate_bpm=95, hl__pulse__h1=0.3))
    assert len(result["compounds"]) <= 3


def test_compound_pulse_single_label():
    """只有 1 个脉 → 无相兼脉。"""
    # 只触发一个脉：rate=105 → ji
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105))
    assert len(result["compounds"]) == 0


# —— H. 八轴信号映射（4 用例） ——


def test_axis_signals_mapping():
    """多脉象时轴信号取最高 confidence。"""
    # ji (A气化, 0.9) + xian (A气化, F正邪, 0.8)
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105, hl__pulse__h3_h1=0.9))
    assert "A气化" in result["axis_signals"]
    # A气化 应该取 ji 的 0.9（最高）
    assert result["axis_signals"]["A气化"] == 0.9


def test_axis_signals_empty():
    """无脉象时轴信号为空。"""
    result = classify_pulse(_feats())
    assert result["axis_signals"] == {}


def test_axis_signals_sorted():
    """返回时按轴 ID 排序。"""
    # 构造多个轴信号
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105, hl__pulse__h3_h1=0.9))
    keys = list(result["axis_signals"].keys())
    assert keys == sorted(keys), f"轴信号应按 key 排序: {keys}"


def test_axis_signals_confidence_rounding():
    """confidence 保留 2 位小数。"""
    # 构造一个会产生非整数置信度的场景
    result = classify_pulse(_feats(hl__pulse__pause_pattern="irregular", hl__pulse__rate_bpm=75))
    for k, v in result["axis_signals"].items():
        # 检查是否是 2 位小数
        assert round(v, 2) == v, f"{k}: {v} 不是 2 位小数"


# —— I. 养生参考 + 护栏（3 用例） ——


def test_wellness_ref_normal():
    """无脉象时 wellness_ref 为基线参考。"""
    result = classify_pulse(_feats())
    assert "基线" in result["wellness_ref"] or "常见范围" in result["wellness_ref"]


def test_wellness_ref_with_alert():
    """alert 脉时 guardrail 含"尽快咨询"。"""
    result = classify_pulse(_feats(hl__pulse__rate_bpm=105))
    assert "尽快咨询" in result["guardrail"]


def test_wellness_ref_with_watch():
    """watch 脉时 guardrail 含具体参考。"""
    result = classify_pulse(_feats(hl__pulse__h3_h1=0.9))
    # watch 级别应有具体参考内容
    assert len(result["guardrail"]) > 10


# —— J. build_pulse_observation（3 用例） ——


def test_build_observation_success():
    """正常包装。"""
    feats = _feats(hl__pulse__rate_bpm=105)
    result = build_pulse_observation(feats, "user123", "2026-10-15")
    assert result["source"] == "pulse_gateway:user123"
    assert result["recorded_at"] == "2026-10-15"
    assert "pulse_labels" in result
    assert "axis_signals" in result
    assert "severity" in result
    assert "wellness_ref" in result
    assert "guardrail" in result
    assert "raw_features" in result


def test_build_observation_source():
    """source 格式正确。"""
    feats = _feats()
    result = build_pulse_observation(feats, "user456", "2026-10-15")
    assert result["source"] == "pulse_gateway:user456"


def test_build_observation_raw_features():
    """只包含 hl.pulse.* 前缀的字段。"""
    feats = _feats()
    feats["other.field"] = "should_be_excluded"
    feats["hl.pulse.rate_bpm"] = 75
    result = build_pulse_observation(feats, "user789", "2026-10-15")
    for k in result["raw_features"]:
        assert k.startswith("hl.pulse."), f"应只包含 hl.pulse.* 前缀: {k}"
    assert "other.field" not in result["raw_features"]


# —— K. 边界值 + fail-loud（3 用例） ——


def test_classify_pulse_db_unavailable(monkeypatch):
    """DB 不可用时抛 PulseKnowledgeBaseError。"""
    monkeypatch.setattr(pulse_engine, "DB_AVAILABLE", False)
    with pytest.raises(PulseKnowledgeBaseError):
        classify_pulse(_feats())


def test_classify_pulse_empty_features():
    """空 features → 不崩溃，severity 由默认值决定。

    dicrotic 默认 0.0 < 0.5 会触发"涩"(se)，severity="watch"。
    实测行为：空输入不会崩溃，但默认 dicrotic=0.0 触发 se。
    """
    result = classify_pulse({})
    assert "labels" in result
    assert "severity" in result
    # dicrotic 默认 0.0 → se（实测行为）
    assert _has(result, "se")
    assert result["severity"] == "watch"


def test_classify_pulse_neutral_features():
    """中性特征（全部处于正常范围）→ 无标签，severity=normal。"""
    feats = {
        "hl.pulse.rate_bpm": 75,
        "hl.pulse.h1": 0.5,
        "hl.pulse.h3_h1": 0.3,
        "hl.pulse.h4_h1": 0.5,
        "hl.pulse.h5_h1": 0.4,
        "hl.pulse.dicrotic_present": 0.8,  # ≥0.5 不触发 se
        "hl.pulse.ascending_slope": 0.5,
        "hl.pulse.perfusion_index": 0.8,
        "hl.pulse.rhythm_regularity": 0.95,
        "hl.pulse.pause_pattern": "none",
        "hl.pulse.depth": "",
    }
    result = classify_pulse(feats)
    assert result["labels"] == []
    assert result["severity"] == "normal"


def test_classify_pulse_non_numeric_features():
    """非数值特征 → _f 返回默认值，不崩溃。

    实测行为：
    - rate_bpm/h1/h3_h1/ascending_slope/perfusion_index 传非数值 → _f 返回 None，
      对应分支跳过，不触发任何判定。
    - dicrotic_present 有默认 0.0（不是 None），传字符串 "abc" 时 _f 返回 0.0，
      0.0 < 0.5 触发 se → severity="watch"。
    - rhythm_regularity 默认 1.0，传 "" 时 _f 返回 1.0，不触发 <0.6 的 jie。
    """
    feats = {
        "hl.pulse.rate_bpm": "not_a_number",
        "hl.pulse.h1": "abc",
        "hl.pulse.h3_h1": "",
        "hl.pulse.dicrotic_present": "abc",  # → 默认 0.0 → 触发 se
        "hl.pulse.ascending_slope": "xyz",
        "hl.pulse.perfusion_index": "invalid",
        "hl.pulse.rhythm_regularity": "",
        "hl.pulse.pause_pattern": "none",
        "hl.pulse.depth": "",
    }
    # 不应抛出异常
    result = classify_pulse(feats)
    assert "labels" in result
    assert "severity" in result
    # dicrotic 默认 0.0 < 0.5 → se（实测行为）
    assert _has(result, "se")
    assert result["severity"] == "watch"
