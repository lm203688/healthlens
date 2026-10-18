"""中医安全护栏测试（check_safety：十八反 / 十九畏 / 妊娠 / 中西药相互作用）

确定性规则，零外部依赖，可单测、可解释。
"""
import pytest

from app.core.tcm_safety import (
    check_safety,
    norm,
    HERB_SYNONYMS,
    classify_drug,
    classify_food,
)


def test_eight_antagonisms_detected():
    """十八反：甘草 反 海藻 应触发 high 级禁忌。"""
    r = check_safety(herbs=["甘草", "海藻"])
    assert r.has_blocking()
    assert any(f.kind == "incompatibility" for f in r.findings)


def test_nineteen_incompat_detected():
    """十九畏：硫黄 畏 朴硝 应触发 high 级禁忌。"""
    r = check_safety(herbs=["硫黄", "朴硝"])
    assert r.has_blocking()


def test_formula_incompatibility():
    """复方：附子（乌头）与半夏同方属十八反。"""
    r = check_safety(formulas=[["附子", "干姜", "甘草", "半夏"]])
    assert r.has_blocking()


def test_pregnancy_contra():
    """妊娠禁忌：附子/红花 属禁用，孕期应拦截。"""
    r = check_safety(herbs=["附子", "红花"], pregnancy=True)
    assert r.has_blocking()
    assert any(f.kind == "pregnancy" for f in r.findings)


def test_drug_interaction_warfarin_danshen():
    """中西药相互作用：丹参 增强华法林抗凝（high）。"""
    r = check_safety(herbs=["丹参"], medications=["华法林"])
    assert any(
        f.kind == "drug_interaction" and f.severity == "high" for f in r.findings
    )


def test_clean_combo_safe():
    """无禁忌组合应判定安全。"""
    r = check_safety(herbs=["人参", "白术", "茯苓"])
    assert not r.has_blocking()


def test_alias_normalization():
    """别名归一：川乌 -> 乌头，应与半夏触发反。"""
    assert norm("川乌") == "乌头"
    r = check_safety(herbs=["川乌", "半夏"])
    assert r.has_blocking()


def test_classify_drug():
    """药品名 -> 交互类别粗略识别。"""
    assert classify_drug("华法林") == "抗凝药/华法林"
    assert classify_drug("氨氯地平") == "降压药"
    assert classify_drug("unknown-xyz") is None


def test_herb_synonyms_chp_expanded():
    """CHP 实体对经典别名做了广度增强，应不少于 87 条。"""
    assert len(HERB_SYNONYMS) >= 87


def test_report_shape():
    """to_dict 结构稳定，便于上层溯源。"""
    r = check_safety(herbs=["甘草", "海藻"])
    d = r.to_dict()
    assert "level" in d and "findings" in d and "has_high_risk" in d
    assert r.source == "tcm_safety"


# ---------------------------------------------------------------------------
# 药-草-食三联相互作用（P1-2，借鉴 DHFI-C 本体思路）
# ---------------------------------------------------------------------------
def test_food_drug_grapefruit_warfarin():
    """葡萄柚 × 华法林：CYP3A4 抑制升高 INR，high。"""
    r = check_safety(foods=["葡萄柚"], medications=["华法林"])
    assert any(
        f.kind == "food_interaction" and f.severity == "high" for f in r.findings
    )


def test_food_drug_alcohol_sulfonylurea():
    """酒精 × 磺脲类降糖药：迟发性低血糖，high。"""
    r = check_safety(foods=["酒"], medications=["二甲双胍"])
    assert any(
        f.kind == "food_interaction" and f.severity == "high" for f in r.findings
    )


def test_food_herb_radish_ginseng():
    """萝卜 × 人参：传统理论破气，low（非临床结论）。"""
    r = check_safety(herbs=["人参"], foods=["萝卜"])
    assert any(
        f.kind == "food_interaction" and f.severity == "low" for f in r.findings
    )


def test_food_herb_salt_licorice():
    """高盐食物 × 甘草：加重水钠潴留，moderate。"""
    r = check_safety(herbs=["甘草"], foods=["咸菜"])
    assert any(
        f.kind == "food_interaction" and f.severity == "moderate" for f in r.findings
    )


def test_food_interaction_clean_no_false_positive():
    """无相关食物/药物组合不应误报 food_interaction。"""
    r = check_safety(herbs=["人参", "白术"], foods=["苹果"])
    assert not any(f.kind == "food_interaction" for f in r.findings)


def test_classify_food():
    """食物名归一到 canonical。"""
    assert classify_food("西柚") == "葡萄柚"
    assert classify_food("牛奶") == "牛奶/乳制品"
    assert classify_food("unknown-food-xyz") is None
