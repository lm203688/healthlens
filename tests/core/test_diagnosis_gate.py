"""解释↔诊断边界层测试（定位重构 2026-11-04）"""
import os
import sys

import pytest

from app.core.diagnosis_gate import (
    DiagnosisGate,
    DiagnosisGateResponse,
    InterpretationResult,
    GateState,
)


class TestDiagnosisGate:
    def test_gate_default_inactive(self):
        """默认门控为 inactive（不激活，留接口）。"""
        gate = DiagnosisGate(active=False)
        assert gate.active is False

    def test_interpret_always_available(self):
        """解释层永远可用（平台核心能力，非医疗器械行为）。"""
        gate = DiagnosisGate(active=False)
        result = gate.interpret(
            axis_scores={"A": 82},
            risk_strata="low",
            deviations=["A 轴轻微偏离"],
            trend_alerts=["血糖呈上升趋势"],
            summary="八轴状态解读",
        )
        assert isinstance(result, InterpretationResult)
        assert result.is_diagnosis is False
        assert result.risk_strata == "low"
        assert result.axis_scores == {"A": 82}

    def test_diagnose_inactive_fail_closed(self):
        """门控未激活时 diagnose 不执行诊断逻辑，返回 not_active。"""
        gate = DiagnosisGate(active=False)
        resp = gate.diagnose({"some": "payload"})
        assert isinstance(resp, DiagnosisGateResponse)
        assert resp.activated is False
        assert resp.state == GateState.INACTIVE.value
        assert resp.reason == "diagnosis_gate_inactive"
        assert resp.result is None  # 无诊断输出

    def test_diagnose_active_but_no_provider(self):
        """门控激活后若无诊断提供方，仍不产生诊断结论。"""
        gate = DiagnosisGate(active=True)
        resp = gate.diagnose({"some": "payload"})
        assert resp.activated is True
        assert resp.state == GateState.ACTIVE.value
        # 框架未注册提供方，不返回诊断结论
        assert resp.result is None or "provider_not_registered" in str(resp.result)

    def test_env_activation(self, monkeypatch):
        """环境变量可激活门控。"""
        monkeypatch.setenv("HEALTHLENS_DIAGNOSIS_GATE", "1")
        gate = DiagnosisGate()
        assert gate.active is True

    def test_env_off_by_default(self, monkeypatch):
        """未设置环境变量默认关闭。"""
        monkeypatch.delenv("HEALTHLENS_DIAGNOSIS_GATE", raising=False)
        gate = DiagnosisGate()
        assert gate.active is False


class TestDiagnosisEngineWording:
    def test_engine_docstring_no_diagnosis_claim(self):
        """引擎文档不再宣称"诊断"。"""
        import inspect
        from app.core.diagnosis_engine import WesternDiagnosisEngine

        doc = inspect.getdoc(WesternDiagnosisEngine) or ""
        assert "诊断" not in doc
        assert "评估" in doc or "健康评估" in doc

    def test_finding_kind_is_risk(self):
        """评估结果 kind 恒为 risk_finding（非 diagnosis）。"""
        from app.core.diagnosis_engine import WesternDiagnosisEngine

        engine = WesternDiagnosisEngine()
        findings = engine.assess_from_observations([
            {"loinc_code": "2345-7", "loinc_name": "空腹血糖", "value_numeric": 7.8,
             "reference_range_high": 6.1, "reference_range_low": 3.9},
        ])
        assert len(findings) > 0
        for f in findings:
            assert f.kind == "risk_finding"