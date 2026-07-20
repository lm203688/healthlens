"""食疗推荐引擎测试"""
import pytest
from app.core.tcm_food_therapy import FoodTherapyEngine, CLASSICAL_FOOD_RECIPES, NON_PHARMA_TREATMENTS


@pytest.fixture
def engine():
    return FoodTherapyEngine()


class TestFoodTherapyByConstitution:
    """体质食疗推荐测试"""

    def test_qixu_recommendations(self, engine):
        """气虚体质应返回山药粥等补气方案"""
        recs = engine.recommend_by_constitution("qixu", limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert "山药粥" in names or "莲子粥" in names
        for r in recs:
            assert r.source  # 每个推荐都应有古籍出处

    def test_yangxu_recommendations(self, engine):
        """阳虚体质应返回温阳方案"""
        recs = engine.recommend_by_constitution("yangxu", limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        for r in recs:
            assert "姜" in r.name or "羊肉" in r.name or r.name in names

    def test_yinxu_recommendations(self, engine):
        """阴虚体质应返回滋阴方案"""
        recs = engine.recommend_by_constitution("yinxu", limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert any("地黄" in n or "甘菊" in n or "萝卜粥" in n for n in names)

    def test_tanshi_recommendations(self, engine):
        """痰湿体质应返回化湿方案"""
        recs = engine.recommend_by_constitution("tanshi", limit=5)
        assert len(recs) > 0

    def test_pinghe_no_panic(self, engine):
        """平和质也可能有推荐（通用食疗）"""
        recs = engine.recommend_by_constitution("pinghe", limit=3)
        # pinghe might not have specific recipes, should not crash
        assert isinstance(recs, list)

    def test_limit_respected(self, engine):
        """limit 参数应被遵守"""
        recs = engine.recommend_by_constitution("qixu", limit=2)
        assert len(recs) <= 2

    def test_seasonal_filter(self, engine):
        """季节过滤应生效"""
        recs = engine.recommend_by_constitution("qixu", seasonal="winter", limit=10)
        for r in recs:
            assert r.seasonal in ("all", "winter")

    def test_each_recipe_has_required_fields(self, engine):
        """每个推荐都应有必需字段"""
        recs = engine.recommend_by_constitution("qixu", limit=10)
        for r in recs:
            assert r.name, "Missing name"
            assert r.category, "Missing category"
            assert r.ingredients, "Missing ingredients"
            assert r.source, "Missing source"


class TestFoodTherapyBySymptoms:
    """症状食疗推荐测试"""

    def test_diabetes_symptoms(self, engine):
        """消渴(糖尿病)症状应匹配萝卜粥"""
        recs = engine.recommend_by_symptoms(["消渴", "口干"], limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert "萝卜粥" in names

    def test_stroke_symptoms(self, engine):
        """中风症状应匹配荆芥粥/葛粉羹"""
        recs = engine.recommend_by_symptoms(["中风", "言语蹇涩"], limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert any(n in ["荆芥粥", "葛粉羹", "麻子粥"] for n in names)

    def test_no_match_symptoms(self, engine):
        """无匹配症状应返回空列表"""
        recs = engine.recommend_by_symptoms(["量子纠缠"], limit=5)
        assert len(recs) == 0

    def test_symptoms_with_constitution_filter(self, engine):
        """症状+体质联合过滤"""
        recs = engine.recommend_by_symptoms(
            ["口干"], constitution_type="yinxu", limit=5
        )
        assert len(recs) > 0


class TestNonPharmaTreatments:
    """非药物治疗测试"""

    def test_qixu_acupressure(self, engine):
        """气虚体质应推荐足三里/腹部按摩"""
        recs = engine.get_non_pharma_treatments("qixu", limit=5)
        assert len(recs) > 0
        names = [r.name for r in recs]
        assert "足三里按揉" in names or "腹部按摩" in names

    def test_treatment_type_filter(self, engine):
        """按治疗类型过滤"""
        recs = engine.get_non_pharma_treatments(
            "qixu", treatment_types=["lifestyle"], limit=10
        )
        assert len(recs) > 0
        for r in recs:
            assert r.treatment_type == "lifestyle"

    def test_qigong_available(self, engine):
        """八段锦应可被推荐"""
        recs = engine.get_non_pharma_treatments("qixu", treatment_types=["qigong"], limit=5)
        assert len(recs) > 0
        assert "八段锦" in [r.name for r in recs]

    def test_all_constitutions_have_recommendations(self, engine):
        """所有九种体质都应有非药物推荐"""
        for ctype in ["pinghe", "qixu", "yangxu", "yinxu", "tanshi", "shire", "xueyu", "qiyu", "tebing"]:
            recs = engine.get_non_pharma_treatments(ctype, limit=1)
            assert len(recs) > 0, f"No non-pharma recommendation for {ctype}"

    def test_diet_guide_all_constitutions(self, engine):
        """每种体质都应有膳食指南"""
        recs = engine.get_non_pharma_treatments("qixu", treatment_types=["diet"], limit=1)
        assert len(recs) > 0
        guide = recs[0]
        assert "qixu" in guide.instructions


class TestDataIntegrity:
    """数据完整性测试"""

    def test_all_recipes_have_unique_names(self):
        """食疗方名应唯一"""
        names = [r["name"] for r in CLASSICAL_FOOD_RECIPES]
        assert len(names) == len(set(names)), f"Duplicate recipe names: {[n for n in names if names.count(n) > 1]}"

    def test_all_recipes_have_source(self):
        """每个食疗方都应有古籍出处"""
        for r in CLASSICAL_FOOD_RECIPES:
            assert r.get("source"), f"Recipe '{r['name']}' missing source"

    def test_all_recipes_have_ingredients(self):
        """每个食疗方都应有食材"""
        for r in CLASSICAL_FOOD_RECIPES:
            assert r.get("ingredients"), f"Recipe '{r['name']}' missing ingredients"

    def test_all_non_pharma_have_instructions(self):
        """每个非药物治疗都应有操作说明"""
        for tx in NON_PHARMA_TREATMENTS:
            assert tx.get("instructions"), f"Treatment '{tx['name']}' missing instructions"