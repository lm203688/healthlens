"""方剂引擎 CHP 饮片集成测试

P1 续：把 6,207 条 CHP 饮片实体接入 tcm_formula_engine / risk_engine，
支持性味归经查询、别名归一与配伍禁忌推理。
"""
import pytest

from app.core.tcm_formula_engine import FormulaEngine, _CHP_INDEX, _CHP_SYN


def test_chp_index_loaded():
    """CHP 饮片实体库已载入（6,207 条）。"""
    assert len(_CHP_INDEX) >= 6207


def test_herb_db_merged():
    """策展 15 味 + CHP 饮片合并进药材库。"""
    db = FormulaEngine()._get_herb_database()
    assert len(db) >= 6207


def test_chp_herb_info_altai():
    """CHP 饮片「阿尔泰多榔菊」药性可被查询（性温、归肺经）。"""
    info = FormulaEngine().get_herb_info("阿尔泰多榔菊")
    assert info is not None
    assert info["nature"] == "温"
    assert "Lung" in info["meridian_tropism"]


def test_alias_normalization_get_herb():
    """别名归一：川乌 -> 乌头，应在 CHP 中查得。"""
    info = FormulaEngine().get_herb_info("川乌")
    assert info is not None


def test_check_compatibility_blocks_eight_antagonism():
    """配伍禁忌推理：甘草 + 海藻 应拦截（十八反）。"""
    res = FormulaEngine().check_compatibility(["甘草", "海藻"])
    assert res["safe"] is False
    assert res["report"]["has_high_risk"] is True


def test_check_compatibility_safe_pair():
    """安全组合：人参 + 白术 + 茯苓 应放行。"""
    res = FormulaEngine().check_compatibility(["人参", "白术", "茯苓"])
    assert res["safe"] is True


def test_syn_index_consistency():
    """别名索引与实际实体名一致。"""
    for canon in _CHP_SYN.values():
        assert canon in _CHP_INDEX
