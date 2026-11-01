"""外部参考数据库接入层契约测试。

分层：
  - **离线用例（默认全跑）**：缓存/限流/错误码/入参校验/ZIP 解包/阈值分档/
    无许可降级/API 契约。全部不联网，可在 CI 稳定运行。
  - **联网用例（`@pytest.mark.live`，默认跳过）**：真实打 RCSB/PubChem/UniProt。
    启用方式：`HL_LIVE_BIO=1 pytest tests/connectors -m live`

为什么要锁这些点：
  1. BLAST 的 JSON2 是 ZIP 包装——这是最容易写错且最难发现的地方，
     一旦上游格式微调，必须由测试先报警，而不是线上返回空结果。
  2. Schrödinger 无许可时必须报错而不是返回空——历史上本项目的静默
     except 吞掉过 axis scorer 的失败，这里用测试把"不伪造"钉死。
  3. 错误码是前后端契约，不能被随手改名。
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import zipfile

import pytest

from app.connectors.reference import ERROR_CODES, ReferenceError, get_source
from app.connectors.reference.alphafold import _band
from app.connectors.reference.base import RateLimiter, TTLCache
from app.connectors.reference.blast import NCBIBlast, _clean_sequence, _parse_report
from app.connectors.reference.pubchem import _looks_like_cas
from app.connectors.reference.rcsb import RCSBPDB
from app.connectors.reference.schrodinger import MODULES, SchrodingerCADD

LIVE = pytest.mark.skipif(
    os.getenv("HL_LIVE_BIO") != "1",
    reason="联网用例：设置 HL_LIVE_BIO=1 后启用",
)


# ---------------------------------------------------------------------------
# 基础设施：缓存 / 限流 / 错误模型
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ttl_cache_expires():
    cache = TTLCache()
    await cache.set("k", {"v": 1}, ttl=0.05)
    assert await cache.get("k") == {"v": 1}
    await asyncio.sleep(0.08)
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_ttl_cache_evicts_when_full():
    cache = TTLCache(max_entries=10)
    for i in range(20):
        await cache.set(f"k{i}", i, ttl=60)
    assert cache.size() <= 10


@pytest.mark.asyncio
async def test_rate_limiter_enforces_interval():
    limiter = RateLimiter(0.05)
    start = asyncio.get_event_loop().time()
    for _ in range(3):
        await limiter.acquire()
    elapsed = asyncio.get_event_loop().time() - start
    # 3 次调用至少产生 2 个间隔
    assert elapsed >= 0.09


def test_reference_error_shape():
    exc = ReferenceError("not_found", "rcsb_pdb", "PDB 4XYZ 不存在", status=404)
    payload = exc.to_dict()
    assert payload["ok"] is False
    assert payload["code"] == "not_found"
    assert payload["source"] == "rcsb_pdb"
    assert payload["upstream_status"] == 404
    assert payload["message"] == ERROR_CODES["not_found"]


def test_reference_error_unknown_code_falls_back():
    exc = ReferenceError("some_new_code", "x")
    assert exc.code == "upstream_error"


# ---------------------------------------------------------------------------
# RCSB PDB
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [("4hhb", "4HHB"), (" 1A1U ", "1A1U"), ("2PGH", "2PGH")])
def test_rcsb_id_normalization(raw, expected):
    assert RCSBPDB._normalize_id(raw) == expected


@pytest.mark.parametrize("bad", ["", "12", "TOOLONG", "4HH!", None])
def test_rcsb_id_rejects_invalid(bad):
    with pytest.raises(ReferenceError) as ei:
        RCSBPDB._normalize_id(bad)  # type: ignore[arg-type]
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_rcsb_search_requires_condition():
    with pytest.raises(ReferenceError) as ei:
        await get_source("rcsb_pdb").search()
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_rcsb_search_limit_bounds():
    with pytest.raises(ReferenceError) as ei:
        await get_source("rcsb_pdb").search(text="hemoglobin", limit=500)
    assert ei.value.code == "invalid_input"


# ---------------------------------------------------------------------------
# BLAST
# ---------------------------------------------------------------------------

def test_blast_sequence_cleaning():
    assert _clean_sequence("ATGC\nATGC  ATGC") == "ATGCATGCATGC"


def test_blast_sequence_rejects_short():
    with pytest.raises(ReferenceError) as ei:
        _clean_sequence("ATGC")
    assert ei.value.code == "invalid_input"


def test_blast_sequence_rejects_illegal_chars():
    # Z/Q 是合法 IUPAC 简并碱基，不能用它们做反例
    with pytest.raises(ReferenceError) as ei:
        _clean_sequence("ATGC@#$%^&ATGC")
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_blast_rejects_unknown_program():
    with pytest.raises(ReferenceError) as ei:
        await NCBIBlast().submit("ATGCATGCATGC", program="blastq")
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_blast_rejects_incompatible_database():
    with pytest.raises(ReferenceError) as ei:
        await NCBIBlast().submit("ATGCATGCATGC", program="blastn", database="swissprot")
    assert ei.value.code == "invalid_input"


def _fake_report() -> dict:
    return {
        "program": "blastn",
        "version": "BLASTN 2.17.0+",
        "search_target": {"db": "core_nt"},
        "query_ID": "Query_1",
        "params": {"expect": 10},
        "results": {
            "search": {
                "hits": [
                    {
                        "description": [{"accession": "PQ040393", "title": "Homo sapiens ACTB mRNA"}],
                        "taxid": 9606,
                        "hsps": [
                            {
                                "evalue": 3.84527e-156,
                                "bit_score": 564.348,
                                "identity": 305,
                                "align_len": 305,
                                "gaps": 0,
                                "query_from": 1,
                                "query_to": 305,
                                "hit_from": 193,
                                "hit_to": 497,
                                "query_strand": "Plus",
                                "hit_strand": "Plus",
                            }
                        ],
                    }
                ]
            }
        },
    }


def test_blast_parse_report_extracts_hits():
    parsed = _parse_report(_fake_report())
    assert parsed["program"] == "blastn"
    assert parsed["database"] == "core_nt"
    assert parsed["hit_count"] == 1
    hit = parsed["hits"][0]
    assert hit["accession"] == "PQ040393"
    assert hit["best_evalue"] == pytest.approx(3.84527e-156)
    assert hit["hsps"][0]["hit_range"] == [193, 497]


def _zip_bytes(index: dict, report: dict, rid: str = "RID123") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{rid}.json", json.dumps(index))
        zf.writestr(f"{rid}_1.json", json.dumps(report))
    return buf.getvalue()


class _FakeResp:
    def __init__(self, content: bytes):
        self.content = content


@pytest.mark.asyncio
async def test_blast_fetch_unwraps_zip(monkeypatch):
    """JSON2 是 ZIP 包装——必须按索引里的 File 指针跳转，不能直接 json.loads。"""
    payload = _zip_bytes(
        {"BlastJSON": [{"File": "RID123_1.json"}]},
        {"BlastOutput2": {"report": _fake_report()}},
    )
    blast = NCBIBlast()

    async def fake_request(*args, **kwargs):
        return _FakeResp(payload)

    monkeypatch.setattr(blast, "_request", fake_request)
    result = await blast.fetch("RID123")
    assert result["report_count"] == 1
    assert result["reports"][0]["hits"][0]["accession"] == "PQ040393"


@pytest.mark.asyncio
async def test_blast_fetch_rejects_non_zip(monkeypatch):
    blast = NCBIBlast()

    async def fake_request(*args, **kwargs):
        return _FakeResp(b'{"Status":"WAITING"}')

    monkeypatch.setattr(blast, "_request", fake_request)
    with pytest.raises(ReferenceError) as ei:
        await blast.fetch("RID123")
    assert ei.value.code in {"parse_error", "upstream_error"}


# ---------------------------------------------------------------------------
# PubChem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [("50-78-2", True), ("64-17-5", True), ("7732-18-5", True), ("50-78-3", False), ("aspirin", False)],
)
def test_cas_number_validation(value, expected):
    assert _looks_like_cas(value) is expected


@pytest.mark.asyncio
async def test_pubchem_rejects_bad_namespace():
    with pytest.raises(ReferenceError) as ei:
        await get_source("pubchem").resolve("aspirin", namespace="cas")
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_pubchem_rejects_empty_query():
    with pytest.raises(ReferenceError) as ei:
        await get_source("pubchem").resolve("   ")
    assert ei.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_pubchem_similar_threshold_bounds():
    with pytest.raises(ReferenceError) as ei:
        await get_source("pubchem").similar("CCO", threshold=0)
    assert ei.value.code == "invalid_input"


# ---------------------------------------------------------------------------
# AlphaFold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "plddt,band",
    [(95.0, "very_high"), (85.0, "confident"), (60.0, "low"), (10.0, "very_low"), (None, "unknown")],
)
def test_plddt_banding(plddt, band):
    assert _band(plddt)[0] == band


# ---------------------------------------------------------------------------
# Schrödinger：无许可必须诚实报错
# ---------------------------------------------------------------------------

def test_schrodinger_not_installed_reports_unusable():
    caps = asyncio.run(SchrodingerCADD(root="").capabilities())
    assert caps["installed"] is False
    assert caps["usable"] is False
    assert caps["installed_module_count"] == 0


@pytest.mark.asyncio
async def test_schrodinger_run_job_raises_license_unavailable():
    with pytest.raises(ReferenceError) as ei:
        await SchrodingerCADD(root="").run_job("glide", ["-HOST", "localhost"])
    assert ei.value.code == "license_unavailable"


@pytest.mark.asyncio
async def test_schrodinger_unknown_module():
    with pytest.raises(ReferenceError) as ei:
        await SchrodingerCADD(root="").run_job("quantum_magic", [])
    assert ei.value.code == "not_implemented"


def test_schrodinger_module_registry_covers_requested_workflow():
    """用户要求的 CADD 工作流必须都在模块表里，缺一个就是能力缺口。"""
    required = {
        "prepwizard", "ligprep", "epik", "glide", "prime_mmgbsa",
        "desmond", "qikprop", "sitemap", "watermap", "fep_plus",
    }
    assert required <= set(MODULES)


# ---------------------------------------------------------------------------
# API 契约
# ---------------------------------------------------------------------------

def test_bio_openapi_contract():
    from app import create_app

    spec = create_app().openapi()
    bio_paths = {p for p in spec["paths"] if p.startswith("/api/v1/bio")}
    expected = {
        "/api/v1/bio/sources",
        "/api/v1/bio/pdb/{pdb_id}",
        "/api/v1/bio/pdb/search",
        "/api/v1/bio/pdb/by-uniprot/{accession}",
        "/api/v1/bio/compound",
        "/api/v1/bio/compound/{cid}",
        "/api/v1/bio/compound/{cid}/synonyms",
        "/api/v1/bio/compound/similar",
        "/api/v1/bio/blast",
        "/api/v1/bio/blast/{rid}/status",
        "/api/v1/bio/blast/{rid}/result",
        "/api/v1/bio/blast/run",
        "/api/v1/bio/protein/{accession}",
        "/api/v1/bio/protein/gene/{symbol}",
        "/api/v1/bio/structure/predicted/{accession}",
        "/api/v1/bio/target/{gene_symbol}",
        "/api/v1/bio/cadd/capabilities",
        "/api/v1/bio/cadd/jobs",
    }
    assert expected <= bio_paths, f"缺失端点: {expected - bio_paths}"


def test_bio_error_status_mapping():
    from app.api.bio import _http

    assert _http(ReferenceError("not_found", "x")).status_code == 404
    assert _http(ReferenceError("invalid_input", "x")).status_code == 400
    assert _http(ReferenceError("rate_limited", "x")).status_code == 429
    assert _http(ReferenceError("timeout", "x")).status_code == 504
    assert _http(ReferenceError("license_unavailable", "x")).status_code == 501
    assert _http(ReferenceError("upstream_error", "x")).status_code == 502


def test_sources_registry_lists_all():
    from app.connectors.reference import list_sources

    names = {cap.source for cap in list_sources()}
    assert names == {
        "rcsb_pdb", "pubchem", "ncbi_blast", "uniprot", "alphafold", "schrodinger"
    }


# ---------------------------------------------------------------------------
# 联网用例（默认跳过）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("HL_LIVE_BIO") != "1", reason="联网用例：HL_LIVE_BIO=1 启用")
async def test_live_rcsb_describe_4hhb():
    data = await get_source("rcsb_pdb").describe("4HHB")
    assert data["pdb_id"] == "4HHB"
    assert "X-RAY DIFFRACTION" in data["experimental_methods"]
    assert data["resolution_angstrom"] == pytest.approx(1.74, abs=0.01)
    assert any(l["comp_id"] == "HEM" for l in data["ligands"])


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("HL_LIVE_BIO") != "1", reason="联网用例：HL_LIVE_BIO=1 启用")
async def test_live_pubchem_aspirin():
    data = await get_source("pubchem").describe("aspirin")
    assert data["compound"]["cid"] == 2244
    assert data["compound"]["molecular_formula"] == "C9H8O4"
    assert "50-78-2" in data["cas_numbers"]


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("HL_LIVE_BIO") != "1", reason="联网用例：HL_LIVE_BIO=1 启用")
async def test_live_uniprot_tp53():
    data = await get_source("uniprot").resolve_gene("TP53")
    assert data["accession"] == "P04637"
    assert data["length"] == 393


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("HL_LIVE_BIO") != "1", reason="联网用例：HL_LIVE_BIO=1 启用")
async def test_live_alphafold_p53():
    data = await get_source("alphafold").predictions("P04637")
    assert data["model_count"] >= 1
    assert data["evidence_type"] == "predicted"
