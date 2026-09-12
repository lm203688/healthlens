"""ClinPGx/CPIC 客户端测试

覆盖两条关键路径, 均不依赖外网:
1. 离线/失败回退: 网络异常时 enrich 返回原样数据, 不抛错、不阻断。
2. 解析已缓存 JSON: 命中 CPIC pair_view 时正确提取 cpiclevel / guideline_name 并附加到用药建议。
"""
import asyncio

import pytest

from app.core import clinpgx_client as c


def test_offline_fallback_pairs(monkeypatch):
    def boom(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(c, "_get_json", boom)
    assert c.get_gene_drug_pairs("CYP2C19") is None
    # get_pair_guideline 在 pairs 为空时也返回 None
    assert c.get_pair_guideline("CYP2C19", "氯吡格雷(Clopidogrel)") is None


def test_gene_detail_uses_symbol_query(monkeypatch):
    """回归 (2026-09-10 ECS 实测): `/data/gene/{symbol}` 返 404『No Gene with ID』。
    路径参数只接受 ClinPGx 内部 ID (如 PA124)，按符号查必须用 `?symbol=` 查询形式。"""
    seen = {}

    def capture(url):
        seen["url"] = url
        return {"data": [{"id": "PA124", "symbol": "CYP2C19"}], "status": "success"}

    monkeypatch.setattr(c, "_get_json", capture)
    d = c.get_gene_detail("CYP2C19")
    assert d and d["status"] == "success"
    assert "/data/gene?symbol=CYP2C19" in seen["url"]
    # 不得退化为会 404 的路径参数形式
    assert "/data/gene/CYP2C19" not in seen["url"]


def test_gene_detail_offline_fallback(monkeypatch):
    def boom(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(c, "_get_json", boom)
    assert c.get_gene_detail("CYP2C19") is None


def test_offline_fallback_enrich(monkeypatch):
    def boom(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(c, "_get_json", boom)
    recs = [{"drug_name": "氯吡格雷(Clopidogrel)", "advice": "avoid"}]
    out = asyncio.run(c.enrich_gene_drugs("CYP2C19", recs))
    # 失败回退: 原样返回, 不附加 cpic_level
    assert out == recs
    assert "cpic_level" not in out[0]


def test_parse_cached_pair(monkeypatch):
    sample = [
        {
            "drugname": "Clopidogrel",
            "cpiclevel": "A",
            "clinpgxlevel": "1A",
            "guidelinename": "CPIC Guideline for clopidogrel and CYP2C19",
        }
    ]
    monkeypatch.setattr(c, "_get_json", lambda url: sample)
    g = c.get_pair_guideline("CYP2C19", "氯吡格雷(Clopidogrel)")
    assert g is not None
    assert g.cpic_level == "A"
    assert g.clinpgx_level == "1A"
    assert g.guideline_name.startswith("CPIC")


def test_enrich_attaches_level(monkeypatch):
    sample = [
        {
            "drugname": "Clopidogrel",
            "cpiclevel": "A",
            "clinpgxlevel": "1A",
            "guidelinename": "CPIC Guideline for clopidogrel and CYP2C19",
        }
    ]
    monkeypatch.setattr(c, "_get_json", lambda url: sample)
    recs = [{"drug_name": "氯吡格雷(Clopidogrel)", "advice": "avoid"}]
    out = asyncio.run(c.enrich_gene_drugs("CYP2C19", recs))
    assert out[0].get("cpic_level") == "A"
    assert out[0].get("guideline_name", "").startswith("CPIC")


def test_enrich_no_cross_lang_match(monkeypatch):
    """英文药名不在本地 drug_name 中时不误匹配。"""
    sample = [{"drugname": "Warfarin", "cpiclevel": "A"}]
    monkeypatch.setattr(c, "_get_json", lambda url: sample)
    recs = [{"drug_name": "氯吡格雷(Clopidogrel)"}]
    out = asyncio.run(c.enrich_gene_drugs("CYP2C19", recs))
    assert "cpic_level" not in out[0]


def test_engine_enriched_offline(monkeypatch):
    """PGxEngine.analyze_user_genome_enriched 在离线时回退且不抛错。"""
    from app.core.pgx_engine import PGxEngine

    def boom(url):
        raise RuntimeError("offline")

    monkeypatch.setattr(c, "_get_json", boom)
    engine = PGxEngine()
    variants = [
        {"gene_symbol": "CYP2C19", "genotype": "*2/*2"},
        {"gene_symbol": "CYP2D6", "genotype": "*1/*1"},
    ]
    results = asyncio.run(engine.analyze_user_genome_enriched(variants))
    assert len(results) == 2
    # 离线回退: 不附加 guidelines_attached 标记
    assert all("guidelines_attached" not in r for r in results)
