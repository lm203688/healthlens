"""中医诊断引擎测试"""
import pytest
from app.core.tcm_engine import TcmDiagnosisEngine, CONSTITUTION_DIMENSIONS, TcmConstitutionResult


class TestTcmEngine:
    def test_nine_constitution_types(self):
        """应包含九种体质"""
        assert len(CONSTITUTION_DIMENSIONS) == 9
        expected = ["pinghe", "qixu", "yangxu", "yinxu", "tanshi",
                     "shire", "xueyu", "qiyu", "tebing"]
        for key in expected:
            assert key in CONSTITUTION_DIMENSIONS

    def test_analyze_constitution(self):
        """体质分析应返回评分"""
        engine = TcmDiagnosisEngine()
        questionnaire = {
            "answers": {
                "dim_pinghe": [2, 2, 2],  # 平和得分低
                "dim_qixu": [4, 4, 4],    # 气虚得分高
                "dim_yangxu": [1, 1, 1],
            }
        }
        result = engine.analyze_constitution(questionnaire)
        assert isinstance(result, TcmConstitutionResult)
        assert result.primary_type == "qixu"
        assert "qixu" in result.scores

    @pytest.mark.asyncio
    async def test_diagnose_syndrome(self):
        """辨证分析应返回证型"""
        engine = TcmDiagnosisEngine()
        result = await engine.diagnose_syndrome(
            symptoms=["气短", "乏力", "自汗", "舌淡"],
            constitution="qixu",
        )
        assert result is not None
        assert "syndrome_name" in result
        assert "principle" in result

    def test_recommend_formula(self):
        """方剂推荐应返回方剂信息"""
        engine = TcmDiagnosisEngine()
        formula = engine.recommend_formula(
            "qixu",
            patient_signs={"principle": "补气", "symptoms": "气短乏力"},
        )
        assert formula is not None
        assert "formula" in formula
        assert "composition" in formula

    def test_unknown_constitution(self):
        """未知体质不应崩溃"""
        engine = TcmDiagnosisEngine()
        result = engine.analyze_constitution({})
        assert result is not None
        assert isinstance(result, TcmConstitutionResult)
