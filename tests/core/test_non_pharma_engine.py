"""非药物个性化方案引擎测试（核心交付物，定位重构 2026-11-04）"""
from datetime import date

import pytest

from app.core.non_pharma_engine import (
    DailyPlan,
    NonPharmaPlanEngine,
    PrecisionLevel,
    UserLifestyleProfile,
    determine_precision,
)


class TestPrecisionLevels:
    def test_basic_only_lifestyle(self):
        """仅生活方式画像 → basic 档（大众可用，精度最低）。"""
        profile = UserLifestyleProfile(age=30)
        level, note = determine_precision(profile)
        assert level == PrecisionLevel.BASIC
        assert "生活方式" in note or "精度最低" in note

    def test_standard_with_biomarkers(self):
        """有化验/体检指标 → standard 档。"""
        profile = UserLifestyleProfile(age=45, biomarkers={"glucose": 6.8})
        level, note = determine_precision(profile)
        assert level == PrecisionLevel.STANDARD

    def test_advanced_with_genomics(self):
        """有基因/组学输入 → advanced 档（最高精度）。"""
        profile = UserLifestyleProfile(
            age=40,
            biomarkers={"glucose": 6.8},
            pathway_scores={"AMPK": 0.4},
        )
        level, note = determine_precision(profile)
        assert level == PrecisionLevel.ADVANCED

    def test_every_level_usable(self):
        """每档都可用（抽屉组合核心：不强制全量数据）。"""
        for profile in [
            UserLifestyleProfile(age=30),
            UserLifestyleProfile(age=45, biomarkers={"glucose": 6.5}),
            UserLifestyleProfile(age=50, pathway_scores={"NAD": 0.3}),
        ]:
            plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
            assert isinstance(plan, DailyPlan)
            assert len(plan.actions) >= 5  # 每档都有可执行动作


class TestDailyPlan:
    def test_generate_basic_plan(self):
        """basic 档生成完整日课（6 条基础动作）。"""
        profile = UserLifestyleProfile(age=35)
        plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
        assert plan.precision_level == PrecisionLevel.BASIC
        assert plan.date_iso == "2026-11-04"
        assert len(plan.actions) == 6

    def test_generate_standard_adds_biomarker_adjustments(self):
        """standard 档按生物标志追加分层动作。"""
        profile = UserLifestyleProfile(
            age=50,
            biomarkers={"glucose": 7.2, "total_cholesterol": 6.5},
        )
        plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
        assert plan.precision_level == PrecisionLevel.STANDARD
        # 基础 6 + 血糖调整 + 血脂调整
        assert len(plan.actions) >= 7
        titles = {a.title for a in plan.actions}
        assert "控糖晚餐" in titles
        assert "降脂早餐" in titles

    def test_generate_advanced_adds_genetic(self):
        """advanced 档按基因弱项精调。"""
        profile = UserLifestyleProfile(
            age=42,
            pathway_scores={"AMPK": 0.4},
            gene_axes={"F"},
        )
        plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
        assert plan.precision_level == PrecisionLevel.ADVANCED
        titles = {a.title for a in plan.actions}
        assert "运动增敏" in titles  # AMPK 弱项
        assert "抗炎饮食" in titles  # F 轴弱项

    def test_dedup_actions(self):
        """重复动作去重（同 slot+title）。"""
        profile = UserLifestyleProfile(age=30, biomarkers={"glucose": 6.5})
        plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
        keys = [(a.slot, a.title) for a in plan.actions]
        assert len(keys) == len(set(keys))

    def test_disclaimer_present(self):
        """免责声明必须存在（诚实边界）。"""
        profile = UserLifestyleProfile(age=30)
        plan = NonPharmaPlanEngine().generate(profile, today=date(2026, 11, 4))
        assert "非医疗处方" in plan.disclaimer
        assert "研究性" in plan.disclaimer or "探索性" in plan.disclaimer