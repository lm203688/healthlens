"""PRS/WGS 框架接口测试（基因深度解析占位，合规 gate 前置）"""
import pytest

from app.core.prs_framework import (
    PRSGenomicsFramework,
    PRSResult,
    WGSAnnotation,
    GenomicsGateState,
)


class TestPRSFramework:
    def test_gate_default_pending(self):
        """合规 gate 未过时，state 为 gate_pending。"""
        fw = PRSGenomicsFramework(gate_active=False)
        assert fw.state == GenomicsGateState.GATE_PENDING.value

    def test_assess_prs_gate_pending_no_data(self):
        """gate 未过 → 不处理数据，返回 gate_pending 占位。"""
        fw = PRSGenomicsFramework(gate_active=False)
        result = fw.assess_prs({"rs123": 0.3})
        assert isinstance(result, PRSResult)
        assert result.risk_level == "not_assessed"
        assert result.is_diagnosis is False  # 恒 False，不是诊断
        assert "合规" in result.note or "gate" in result.note.lower()

    def test_assess_prs_honest_risk_not_diagnosis(self):
        """PRS 诚实边界：风险≠诊断，AUC 0.6-0.7。"""
        fw = PRSGenomicsFramework(gate_active=True)
        result = fw.assess_prs()
        assert result.is_diagnosis is False
        # AUC 在 0.6-0.7 典型区间
        assert result.auc_estimate is None or 0.6 <= result.auc_estimate <= 0.7
        assert "非个体诊断" in result.note or "风险" in result.note

    def test_annotate_wgs_gate_pending(self):
        """gate 未过 → WGS 注释不处理数据。"""
        fw = PRSGenomicsFramework(gate_active=False)
        ann = fw.annotate_wgs([{"variant": "x"}])
        assert isinstance(ann, WGSAnnotation)
        assert ann.variants_annotated == 0
        assert ann.pathogenic_graded == 0