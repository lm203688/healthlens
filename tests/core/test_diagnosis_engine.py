"""西医诊断引擎测试"""
import pytest
from app.core.diagnosis_engine import WesternDiagnosisEngine, DiagnosisFinding


class TestWesternDiagnosisEngine:
    def test_diagnose_high_blood_glucose(self):
        """高血糖应触发糖尿病相关诊断"""
        engine = WesternDiagnosisEngine()
        findings = engine.diagnose_from_observations([
            {"loinc_code": "2345-7", "loinc_name": "空腹血糖", "value_numeric": 7.8,
             "reference_range_high": 6.1, "reference_range_low": 3.9},
        ])
        assert len(findings) > 0
        assert any("血糖" in f.name for f in findings)

    def test_diagnose_high_cholesterol(self):
        """高胆固醇应触发高胆固醇血症诊断"""
        engine = WesternDiagnosisEngine()
        findings = engine.diagnose_from_observations([
            {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": 6.8,
             "reference_range_high": 5.2, "reference_range_low": 0},
        ])
        assert len(findings) > 0
        assert any("胆固醇" in f.name for f in findings)

    def test_diagnose_normal_no_findings(self):
        """全部正常不应产生诊断"""
        engine = WesternDiagnosisEngine()
        findings = engine.diagnose_from_observations([
            {"loinc_code": "2345-7", "loinc_name": "空腹血糖", "value_numeric": 5.0,
             "reference_range_high": 6.1, "reference_range_low": 3.9},
            {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": 4.5,
             "reference_range_high": 5.2, "reference_range_low": 0},
        ])
        # 正常值不应产生诊断
        assert len(findings) == 0

    def test_diagnose_empty_input(self):
        """空输入不应崩溃"""
        engine = WesternDiagnosisEngine()
        findings = engine.diagnose_from_observations([])
        assert findings == []

    def test_multiple_abnormalities(self):
        """多个异常应产生多个诊断"""
        engine = WesternDiagnosisEngine()
        findings = engine.diagnose_from_observations([
            {"loinc_code": "2345-7", "loinc_name": "空腹血糖", "value_numeric": 8.0,
             "reference_range_high": 6.1, "reference_range_low": 3.9},
            {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": 6.8,
             "reference_range_high": 5.2, "reference_range_low": 0},
            {"loinc_code": "2085-9", "loinc_name": "甘油三酯", "value_numeric": 2.5,
             "reference_range_high": 1.7, "reference_range_low": 0},
        ])
        assert len(findings) >= 2
        # 验证返回的是 DiagnosisFinding 对象
        for f in findings:
            assert isinstance(f, DiagnosisFinding)
