"""药物基因组学引擎测试"""
import pytest
from app.core.pgx_engine import PGxEngine


def test_cyp2d6_normal_metabolizer():
    """测试 CYP2D6 正常代谢者"""
    engine = PGxEngine()
    result = engine.interpret_genotype("CYP2D6", "*1/*1")
    assert result is not None
    assert result.phenotype == "NM"
    assert result.activity_score == 2.0
    assert len(result.drug_recommendations) > 0


def test_cyp2d6_poor_metabolizer():
    """测试 CYP2D6 差代谢者"""
    engine = PGxEngine()
    result = engine.interpret_genotype("CYP2D6", "*4/*4")
    assert result is not None
    assert result.phenotype == "PM"
    assert result.activity_score == 0.0


def test_cyp2c19_rapid_metabolizer():
    """测试 CYP2C19 快速代谢者"""
    engine = PGxEngine()
    result = engine.interpret_genotype("CYP2C19", "*17/*17")
    assert result is not None
    assert result.phenotype == "RM"
    assert result.activity_score == 3.0


def test_vkorc1_sensitivity():
    """测试 VKORC1 华法林敏感性"""
    engine = PGxEngine()
    result = engine.interpret_genotype("VKORC1", "AA")
    assert result is not None
    assert result.phenotype == "高敏感性"


def test_unknown_gene():
    """测试未知基因"""
    engine = PGxEngine()
    result = engine.interpret_genotype("UNKNOWN_GENE", "*1/*1")
    assert result is None


@pytest.mark.asyncio
async def test_analyze_user_genome():
    """测试批量基因组分析"""
    engine = PGxEngine()
    variants = [
        {"gene": "CYP2D6", "genotype": "*1/*4", "rsid": "rs3892097"},
        {"gene": "CYP2C19", "genotype": "*1/*17", "rsid": "rs12248560"},
        {"gene": "VKORC1", "genotype": "GA", "rsid": "rs9923231"},
    ]
    results = await engine.analyze_user_genome(variants)
    assert len(results) == 3
    # CYP2D6 *1/*4 = IM
    assert results[0]["phenotype"] == "IM"
    # CYP2C19 *1/*17 = RM
    assert results[1]["phenotype"] == "RM"


def test_drug_interactions():
    """测试药物相互作用检测"""
    engine = PGxEngine()
    variants = [
        {"gene": "CYP2D6", "genotype": "*4/*4"},  # PM
        {"gene": "CYP2C19", "genotype": "*1/*1"},  # NM (不应报告)
    ]
    interactions = engine.get_drug_interactions(variants)
    # 只有非 NM 的才报告
    assert len(interactions) > 0
    assert all(i["gene"] == "CYP2D6" for i in interactions)
    assert all(i["severity"] == "high" for i in interactions)
