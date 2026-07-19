from app.core.health_analyzer import HealthAnalyzer

def test_analyze_normal_observations():
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "Glucose", "value_numeric": 90, "value_unit": "mg/dL", "reference_range_low": 70, "reference_range_high": 100},
        {"loinc_code": "2085-9", "loinc_name": "HDL-C", "value_numeric": 55, "value_unit": "mg/dL", "reference_range_low": 40, "reference_range_high": 60},
    ]
    result = analyzer.analyze_observations(observations)
    assert len(result.abnormal_items) == 0
    assert "2 项指标" in result.summary

def test_analyze_abnormal_observations():
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "Glucose", "value_numeric": 150, "value_unit": "mg/dL", "reference_range_low": 70, "reference_range_high": 100},
    ]
    result = analyzer.analyze_observations(observations)
    assert len(result.abnormal_items) == 1
    assert result.abnormal_items[0]["name"] == "Glucose"


def test_risk_factors_empty_when_normal():
    """所有指标正常时 risk_factors 应为空列表"""
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "Glucose", "value_numeric": 5.0, "value_unit": "mmol/L", "reference_range_low": 3.9, "reference_range_high": 6.1},
        {"loinc_code": "718-7", "loinc_name": "Hemoglobin", "value_numeric": 150, "value_unit": "g/L", "reference_range_low": 130, "reference_range_high": 175},
    ]
    result = analyzer.analyze_observations(observations)

    assert result.risk_factors == []
    assert len(result.recommendations) == 1
    assert "正常范围" in result.recommendations[0]


def test_risk_factors_non_empty_when_abnormal():
    """存在异常指标时 risk_factors 应非空，recommendations 应包含建议"""
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "血糖(Glucose)", "value_numeric": 6.8, "value_unit": "mmol/L", "reference_range_low": 3.9, "reference_range_high": 6.1},
        {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": 5.8, "value_unit": "mmol/L", "reference_range_low": 2.8, "reference_range_high": 5.2},
    ]
    result = analyzer.analyze_observations(observations)

    assert len(result.risk_factors) == 2
    assert result.risk_factors[0]["factor"] == "血糖(Glucose)"
    assert result.risk_factors[0]["level"] in ("borderline", "high")
    assert result.risk_factors[1]["factor"] == "总胆固醇"

    # recommendations 不应为空
    assert len(result.recommendations) >= 1
    # 2 项异常，应包含"轻度异常"建议
    assert any("轻度异常" in r for r in result.recommendations)


def test_risk_factors_high_level():
    """明显偏离正常范围时 risk_factor level 应为 high"""
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "血糖(Glucose)", "value_numeric": 15.0, "value_unit": "mmol/L", "reference_range_low": 3.9, "reference_range_high": 6.1},
    ]
    result = analyzer.analyze_observations(observations)

    assert len(result.risk_factors) == 1
    assert result.risk_factors[0]["level"] == "high"
    assert "明显" in result.risk_factors[0]["detail"]


def test_recommendations_for_multiple_abnormal():
    """3 项以上异常时 recommendations 应包含'尽快就医'建议"""
    analyzer = HealthAnalyzer()
    observations = [
        {"loinc_code": "2345-7", "loinc_name": "血糖", "value_numeric": 6.8, "value_unit": "mmol/L", "reference_range_low": 3.9, "reference_range_high": 6.1},
        {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": 5.8, "value_unit": "mmol/L", "reference_range_low": 2.8, "reference_range_high": 5.2},
        {"loinc_code": "2571-8", "loinc_name": "ALT", "value_numeric": 55, "value_unit": "U/L", "reference_range_low": 0, "reference_range_high": 40},
    ]
    result = analyzer.analyze_observations(observations)

    assert len(result.risk_factors) == 3
    assert len(result.recommendations) >= 1
    # 3 项异常，应包含"尽快就医"
    assert any("尽快就医" in r for r in result.recommendations)