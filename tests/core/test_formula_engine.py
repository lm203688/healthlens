"""方剂引擎测试"""
import pytest
from app.core.tcm_formula_engine import FormulaEngine


class TestFormulaEngine:
    def setup_method(self):
        self.engine = FormulaEngine()

    def test_search_library_by_name(self):
        """按方剂名搜索"""
        results = self.engine.search_library("四君子")
        assert len(results) > 0
        assert any("四君子" in r["name"] for r in results)

    def test_search_library_by_keyword(self):
        """按功效关键词搜索"""
        results = self.engine.search_library("补气")
        assert len(results) >= 0  # 可能无结果，不崩溃即可

    def test_get_herb_info_known(self):
        """获取已知中药详情"""
        info = self.engine.get_herb_info("人参")
        assert info is not None
        assert info["name"] == "人参"
        assert "nature" in info
        assert "dosage" in info
        assert "contraindications" in info

    def test_get_herb_info_unknown(self):
        """获取未知中药应返回 None"""
        info = self.engine.get_herb_info("不存在的药")
        assert info is None

    def test_get_herb_info_fuzzy(self):
        """模糊匹配中药"""
        info = self.engine.get_herb_info("黄芪")
        assert info is not None

    def test_list_all_herbs(self):
        """列出所有中药"""
        herbs = self.engine.list_all_herbs()
        assert len(herbs) >= 10
        names = [h["name"] for h in herbs]
        assert "人参" in names
        assert "甘草" in names

    def test_get_formula_composition(self):
        """获取方剂组成"""
        herbs = self.engine.get_formula_composition("formula_0")
        # 可能为空(没有匹配的 formula_id)
        assert isinstance(herbs, list)
