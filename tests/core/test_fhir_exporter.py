"""FHIR 导出器测试 (完善版)"""
import pytest
from app.core.fhir_exporter import FHIRExporter


class TestFHIRExporter:
    def setup_method(self):
        self.exporter = FHIRExporter()

    def test_export_observation_normal(self):
        """正常指标导出"""
        obs = {
            "loinc_code": "8480-6",
            "loinc_name": "收缩压",
            "value_numeric": 120,
            "value_unit": "mmHg",
            "recorded_at": "2026-07-18T10:00:00",
            "user_id": "test-user-id",
        }
        result = self.exporter.export_observation(obs)
        assert result["resourceType"] == "Observation"
        assert result["status"] == "final"
        assert result["subject"]["reference"] == "Patient/test-user-id"
        assert result["valueQuantity"]["value"] == 120.0

    def test_export_observation_abnormal(self):
        """异常指标应标注 interpretation"""
        obs = {
            "loinc_code": "2339-0",
            "loinc_name": "空腹血糖",
            "value_numeric": 8.5,
            "value_unit": "mmol/L",
            "recorded_at": "2026-07-18T10:00:00",
            "is_abnormal": True,
            "user_id": "test-user-id",
        }
        result = self.exporter.export_observation(obs)
        assert result["interpretation"][0]["coding"][0]["code"] == "A"

    def test_export_observation_with_reference_range(self):
        """带参考范围的导出"""
        obs = {
            "loinc_code": "2093-3",
            "loinc_name": "总胆固醇",
            "value_numeric": 5.8,
            "value_unit": "mmol/L",
            "reference_range_low": 0,
            "reference_range_high": 5.2,
        }
        result = self.exporter.export_observation(obs)
        assert result["referenceRange"] is not None

    def test_export_patient_bundle(self):
        """Patient Bundle 导出"""
        user_data = {
            "id": "user-123",
            "name": "张三",
            "gender": "male",
            "birth_date": "1980-01-01",
            "height_cm": 170,
            "weight_kg": 70,
        }
        observations = [
            {"loinc_code": "8480-6", "loinc_name": "收缩压", "value_numeric": 125, "value_unit": "mmHg", "user_id": "user-123"},
            {"loinc_code": "2339-0", "loinc_name": "空腹血糖", "value_numeric": 5.5, "value_unit": "mmol/L", "user_id": "user-123"},
        ]
        bundle = self.exporter.export_patient_bundle(user_data, observations)
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "collection"
        # Patient + 2 Observations + 1 DiagnosticReport = 4 entries
        assert len(bundle["entry"]) == 4

    def test_export_patient_bundle_empty_obs(self):
        """空观测值应无 DiagnosticReport"""
        bundle = self.exporter.export_patient_bundle({"id": "u1", "name": "test"}, [])
        assert bundle["resourceType"] == "Bundle"
        # 只有 Patient
        assert len(bundle["entry"]) == 1
