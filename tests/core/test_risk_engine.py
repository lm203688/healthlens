"""慢病风险评估引擎测试"""
import pytest
from app.core.risk_engine import (
    RiskAssessmentEngine,
    ASCVDRiskEngine,
    DiabetesRiskEngine,
    MetabolicSyndromeEngine,
)


class TestASCVDRiskEngine:
    """ASCVD 风险评估测试"""

    def test_low_risk_young_healthy(self):
        """年轻健康人群应为低风险"""
        engine = ASCVDRiskEngine()
        result = engine.assess(
            age=35, gender="male", sbp=115, tc=4.0,
            hdl_c=1.6, is_smoker=False, has_diabetes=False,
        )
        assert result.risk_type == "ascvd"
        assert result.risk_level == "low"
        assert result.risk_probability < 5.0
        assert len(result.recommendations) > 0

    def test_high_risk_smoker_with_hypertension(self):
        """吸烟+高血压+高血脂应为高风险"""
        engine = ASCVDRiskEngine()
        result = engine.assess(
            age=58, gender="male", sbp=155, tc=6.5,
            hdl_c=0.9, ldl_c=4.3, is_smoker=True,
            has_diabetes=True, waist=95,
        )
        assert result.risk_level in ("high", "very_high")
        assert result.risk_probability > 14.0
        # 应包含吸烟、高血压、糖尿病因素
        factor_names = [f.name for f in result.risk_factors]
        assert "吸烟" in factor_names
        assert "糖尿病" in factor_names

    def test_female_protective_hdl(self):
        """高 HDL-C 有保护作用，扣分"""
        engine = ASCVDRiskEngine()
        result = engine.assess(
            age=50, gender="female", sbp=125, tc=4.5,
            hdl_c=1.8,
        )
        hdl_factor = [f for f in result.risk_factors if f.name == "HDL-C"]
        assert len(hdl_factor) == 1
        assert hdl_factor[0].points == -1  # 保护因素扣分

    def test_recommendations_generated(self):
        """评估结果应包含建议"""
        engine = ASCVDRiskEngine()
        result = engine.assess(
            age=60, gender="male", sbp=140, tc=5.5, is_smoker=True,
        )
        assert len(result.recommendations) >= 3
        assert len(result.references) >= 1


class TestDiabetesRiskEngine:
    """糖尿病风险评估测试"""

    def test_low_risk_young_lean(self):
        """年轻瘦子应为低风险"""
        engine = DiabetesRiskEngine()
        result = engine.assess(
            age=25, gender="male", bmi=21, sbp=115, waist=75,
        )
        assert result.risk_level == "low"
        assert result.risk_probability < 5.0

    def test_high_risk_obese_with_family_history(self):
        """肥胖+家族史应为高风险"""
        engine = DiabetesRiskEngine()
        result = engine.assess(
            age=52, gender="male", bmi=29, sbp=145,
            waist=96, family_history=True,
        )
        assert result.risk_level in ("high", "very_high")
        assert result.risk_probability > 20.0

    def test_waist_gender_specific(self):
        """腰围阈值应区分性别"""
        engine = DiabetesRiskEngine()
        # 男性腰围 90 应计分
        male_result = engine.assess(
            age=45, gender="male", bmi=25, sbp=125, waist=92,
        )
        male_waist_factor = [f for f in male_result.risk_factors if f.name == "腰围"]
        assert len(male_waist_factor) == 1
        assert male_waist_factor[0].points == 2

        # 女性腰围 88 应计分
        female_result = engine.assess(
            age=45, gender="female", bmi=25, sbp=125, waist=88,
        )
        female_waist_factor = [f for f in female_result.risk_factors if f.name == "腰围"]
        assert len(female_waist_factor) == 1
        assert female_waist_factor[0].points == 2


class TestMetabolicSyndromeEngine:
    """代谢综合征评估测试"""

    def test_no_metabolic_syndrome(self):
        """指标全部正常不应诊断为代谢综合征"""
        engine = MetabolicSyndromeEngine()
        result = engine.assess(
            gender="male", waist=80, fpg=5.0,
            sbp=115, dbp=75, tg=1.0, hdl_c=1.5,
        )
        assert result.risk_level == "low"
        assert result.risk_probability < 60.0

    def test_metabolic_syndrome_diagnosis(self):
        """符合3项应诊断为代谢综合征"""
        engine = MetabolicSyndromeEngine()
        result = engine.assess(
            gender="male", waist=95, fpg=6.5,
            sbp=140, dbp=90, tg=1.5, hdl_c=1.2,
        )
        # 腰围≥90 + 血糖≥6.1 + 血压≥130 = 3项
        assert result.risk_level in ("high", "very_high")
        assert result.risk_probability == 100.0

    def test_all_criteria_met(self):
        """5项全部异常应为极高风险"""
        engine = MetabolicSyndromeEngine()
        result = engine.assess(
            gender="male", waist=100, fpg=7.0,
            sbp=150, dbp=95, tg=2.5, hdl_c=0.9,
        )
        assert result.risk_level == "very_high"
        assert result.risk_score == 5.0  # 5项全部符合


class TestRiskAssessmentEngine:
    """总引擎测试"""

    def test_assess_all_returns_multiple_results(self):
        """全量评估应返回多项结果"""
        engine = RiskAssessmentEngine()
        profile = {
            "age": 55, "gender": "male", "bmi": 27,
            "waist": 92, "sbp": 145, "dbp": 92,
            "tc": 5.8, "tg": 2.0, "hdl_c": 1.0, "ldl_c": 3.6,
            "fpg": 6.0, "is_smoker": True,
        }
        results = engine.assess_all(profile)
        # 40岁以上应有 ascvd + diabetes + metabolic_syndrome
        assert "ascvd" in results
        assert "diabetes" in results
        assert "metabolic_syndrome" in results

    def test_young_person_no_ascvd(self):
        """40岁以下不评估 ASCVD"""
        engine = RiskAssessmentEngine()
        profile = {
            "age": 30, "gender": "male", "bmi": 22,
            "waist": 78, "sbp": 115, "tc": 4.0,
        }
        results = engine.assess_all(profile)
        assert "ascvd" not in results
        assert "diabetes" in results

    def test_overall_risk_level(self):
        """总体风险等级应取最高"""
        engine = RiskAssessmentEngine()
        profile = {
            "age": 60, "gender": "male", "bmi": 30,
            "waist": 100, "sbp": 160, "tc": 6.8,
            "is_smoker": True, "has_diabetes": True,
        }
        results = engine.assess_all(profile)
        overall, prob = engine.get_overall_risk_level(results)
        assert overall in ("high", "very_high")
        assert prob > 10.0

    def test_empty_results(self):
        """空结果应返回 unknown"""
        engine = RiskAssessmentEngine()
        overall, prob = engine.get_overall_risk_level({})
        assert overall == "unknown"
        assert prob == 0.0
