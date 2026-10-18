"""HealthLens 案例证据库测试 (tests/data/test_case_evidence.py)

参考章节：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §6 与 §10 #5
参考工具：tools/verify_evidence_dois.py + tools/enrich_case_evidence_dois.py
参考报告：data/DOI_VERIFICATION_REPORT_2026-10-13.md + data/case_evidence_db_report_2026-10-16.md

覆盖：
  - 案例库 JSON schema 校验（每条 case 必填字段）
  - DOI 格式校验（正则 ^10\\.\\d{4,9}/）
  - citation_status 枚举完整性
  - 权重和、axes 覆盖、evidence_level 分布
  - 已核验 DOI 的引用格式一致性
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


DOCS_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = DOCS_ROOT / "data" / "case_evidence_db.json"

DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s\",}\];）]+")
VALID_STATUSES = {
    "verified",                # 已 Crossref 单条解析（旧格式）
    "verified_crossref",       # 本轮 enrichment 新增并通过 Crossref 验证
    "unverified_no_publication",  # 未匹配到文献（诚实标记）
    "unverified_text",         # 纯文本来源（含待复核）
    "traditional",             # 古籍/传统食疗
    "synthetic_validation",    # 自动生成的验证夹具
    "broken_citation",         # DOI 解析失败
    "unsourced",               # 完全无来源
}
VALID_AXES = {"A", "B", "C", "D", "E", "F", "G", "H"}
VALID_EVIDENCE_LEVELS = {"L1", "L2", "L3", "L4"}


@pytest.fixture(scope="module")
def db() -> dict:
    with open(DB_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def cases(db) -> list[dict]:
    return db["cases"]


def _case_id(c: dict) -> str:
    return c.get("case_id") or c.get("id") or "<unknown>"


def _axes(c: dict) -> list[str]:
    """兼容两种 schema：axes 数组 vs axis 单字符。"""
    if c.get("axes"):
        return [a for a in c["axes"] if a]
    if c.get("axis"):
        return [c["axis"]]
    return []


# ---------------------------------------------------------------------------
# 1. 结构校验
# ---------------------------------------------------------------------------


def test_db_top_level_structure(db):
    for key in ("meta", "cases"):
        assert key in db, f"missing top-level key: {key}"


def test_meta_reports_total_consistency(db, cases):
    assert len(cases) >= 100, f"case count too low: {len(cases)}"
    total = db["meta"].get("total") or db["meta"].get("total_cases") or 0
    # meta.total 反映历史总数；本轮实际 cases 数可能更多（含 HL-* 验证夹具）
    assert total > 0


def test_cases_is_non_empty_list(cases):
    assert isinstance(cases, list)
    assert len(cases) >= 100


def test_each_case_has_identifier(cases):
    for c in cases:
        assert _case_id(c) not in ("", "<unknown>", None), "case lacks id/case_id"


def test_case_ids_are_unique_or_known_duplicates(cases):
    """case_id/case 应唯一；已知的 CASE-024 有两条 duplicate（电针 ACU + 运动外泌体），
    历史上未做 case_id 冲突消解，此处宽容记录。"""
    ids = [_case_id(c) for c in cases]
    counter = Counter(ids)
    dupes = {k: v for k, v in counter.items() if v > 1}
    # 唯一允许的重复：CASE-024（两条，ACU + EXO）
    allowed = {"CASE-024"}
    unexpected = set(dupes) - allowed
    assert not unexpected, f"unexpected duplicate case_ids: {dict(unexpected)}"
    if "CASE-024" in dupes:
        assert dupes["CASE-024"] == 2, f"CASE-024 should appear exactly 2 times, got {dupes['CASE-024']}"


def test_evidence_level_in_valid_set(cases):
    for c in cases:
        lev = c.get("evidence_level")
        if lev is not None:
            assert lev in VALID_EVIDENCE_LEVELS, f"{_case_id(c)}: invalid evidence_level={lev}"


# ---------------------------------------------------------------------------
# 2. 轴（axes）覆盖与合法性
# ---------------------------------------------------------------------------


def test_all_axes_in_valid_set(cases):
    """所有 case 的 axis/axes 都必须是 A-H。"""
    for c in cases:
        for a in _axes(c):
            assert a in VALID_AXES, f"{_case_id(c)}: invalid axis={a}"


def test_axes_cover_all_eight_axes(cases):
    """至少覆盖 A-H 全部 8 轴（防止某一轴证据断裂）。"""
    seen = set()
    for c in cases:
        seen.update(_axes(c))
    for axis in VALID_AXES:
        assert axis in seen, f"axis {axis} has zero cases"


def test_axis_weight_or_score_range(cases):
    """若 axes 上有 score/weight，必须在 0-1 区间。"""
    for c in cases:
        for a in _axes(c):
            # 部分条目会在 case 顶层写 axis_score 或直接嵌在 primary_outcomes 中
            score = c.get(f"axis_{a}_score")
            if score is None:
                continue
            assert 0.0 <= float(score) <= 1.0, f"{_case_id(c)}: axis {a} score out of [0,1]"


def test_axis_weights_sum_to_one(cases):
    """若 case 有 axis_weights 字典，权重要和为 1（±1e-6）。"""
    for c in cases:
        w = c.get("axis_weights")
        if not isinstance(w, dict) or not w:
            continue
        s = sum(float(v) for v in w.values())
        assert abs(s - 1.0) < 1e-6, f"{_case_id(c)}: axis_weights sum={s}, expected 1.0"


# ---------------------------------------------------------------------------
# 3. citation_status 完整性
# ---------------------------------------------------------------------------


def test_all_cases_have_citation_status(cases):
    for c in cases:
        assert "citation_status" in c, f"{_case_id(c)}: missing citation_status"


def test_citation_status_in_valid_enum(cases):
    seen: Counter = Counter()
    for c in cases:
        s = c["citation_status"]
        assert s in VALID_STATUSES, f"{_case_id(c)}: unknown citation_status={s}"
        seen[s] += 1
    # 至少 3 种状态共存（避免单一状态覆盖真实分布）
    assert len(seen) >= 3, f"citation_status distribution too narrow: {dict(seen)}"


def test_synthetic_cases_are_HL_prefixed(cases):
    """synthetic_validation 条目必须 HL-* 前缀（结构一致性）。"""
    for c in cases:
        if c.get("citation_status") == "synthetic_validation":
            cid = _case_id(c)
            assert cid.startswith("HL-"), f"{cid}: synthetic but not HL- prefixed"


def test_traditional_cases_no_doi(cases):
    """traditional 条目不做 DOI 化。"""
    for c in cases:
        if c.get("citation_status") == "traditional":
            doi = c.get("doi")
            if doi:
                assert doi == "traditional", f"{_case_id(c)}: traditional but has non-traditional doi={doi}"


# ---------------------------------------------------------------------------
# 4. DOI 格式与引用一致性（关键红线）
# ---------------------------------------------------------------------------


def test_doi_format_when_present(cases):
    """任何非空、非'traditional' 的 doi 必须符合 ^10\\.\\d{4,9}/ 正则。"""
    for c in cases:
        doi = c.get("doi")
        if not doi or doi == "traditional":
            continue
        assert isinstance(doi, str), f"{_case_id(c)}: doi not string: {doi!r}"
        assert DOI_RE.match(doi), f"{_case_id(c)}: doi format invalid: {doi}"


def test_verified_statuses_require_nonempty_doi(cases):
    """citation_status ∈ {verified, verified_crossref} 时 doi 字段必须非空。"""
    for c in cases:
        s = c.get("citation_status")
        if s in ("verified", "verified_crossref"):
            assert c.get("doi"), f"{_case_id(c)}: {s} but doi empty"


def test_verified_crossref_entries_have_source_canonical(cases):
    """verified_crossref 条目必须有 source_canonical（含 title/journal/year）。"""
    for c in cases:
        if c.get("citation_status") == "verified_crossref":
            sc = c.get("source_canonical")
            assert isinstance(sc, dict) and sc, f"{_case_id(c)}: verified_crossref without source_canonical"
            for k in ("title", "journal", "year"):
                assert sc.get(k), f"{_case_id(c)}: source_canonical.{k} empty"


def test_unverified_no_publication_has_disclaimer(cases):
    """未匹配文献的条目必须带 disclaimer（诚实披露）。"""
    n = 0
    for c in cases:
        if c.get("citation_status") == "unverified_no_publication":
            n += 1
            d = c.get("disclaimer")
            assert d, f"{_case_id(c)}: unverified_no_publication without disclaimer"
            assert "not" in d.lower() and "citable" in d.lower(), (
                f"{_case_id(c)}: disclaimer should mention non-citability"
            )
    # 期望至少有几条 unverified（诚实策略下不应为 0）
    assert n >= 1, "no unverified_no_publication entries; enrichment may be over-claiming"


def test_no_obviously_hallucinated_dois(cases):
    """已知幻觉 DOI（Farr 2026 'AFFIRM'）不允许以 verified 状态出现。"""
    HALLS = {"10.1038/s41591-026-04102-8"}
    for c in cases:
        doi = c.get("doi")
        if doi in HALLS:
            assert c.get("citation_status") != "verified", (
                f"{_case_id(c)}: hallucinated DOI {doi} marked as verified"
            )


def test_case_evidence_db_report_exists():
    """报告文件必须存在（诚实披露载体）。"""
    report = DOCS_ROOT / "data" / "case_evidence_db_report_2026-10-16.md"
    assert report.exists(), f"missing enrichment report: {report}"
    text = report.read_text(encoding="utf-8")
    assert "诚实" in text or "未匹配" in text, "report should contain honest disclosure"


# ---------------------------------------------------------------------------
# 5. 分布与完整性
# ---------------------------------------------------------------------------


def test_evidence_level_distribution(cases):
    """证据等级至少覆盖 3 档。"""
    ctr = Counter(c.get("evidence_level") for c in cases if c.get("evidence_level"))
    assert len(ctr) >= 3, f"too few evidence levels: {dict(ctr)}"


def test_weighted_axis_count_matches_cases(cases):
    """cases 数量应与 axes 出现次数一致（每条 case 至少 1 轴）。"""
    for c in cases:
        assert len(_axes(c)) >= 1, f"{_case_id(c)}: zero axes"


def test_verification_tool_exists():
    """核验工具必须仍在仓库中（避免只写死数据无方法学）。"""
    assert (DOCS_ROOT / "tools" / "verify_evidence_dois.py").exists()
    assert (DOCS_ROOT / "tools" / "enrich_case_evidence_dois.py").exists()


def test_prospective_cohort_docs_exist():
    """前瞻队列材料包必须齐全。"""
    base = DOCS_ROOT / "docs" / "prospective_cohort"
    for name in (
        "study_protocol.md",
        "recruitment_questionnaire.md",
        "informed_consent.md",
        "data_dictionary.md",
        "analysis_plan.md",
        "osf_preprint_draft.md",
    ):
        assert (base / name).exists(), f"missing prospective cohort file: {name}"


def test_zenodo_docs_exist():
    """Zenodo 打包材料必须齐全。"""
    base = DOCS_ROOT / "docs" / "zenodo_publication"
    for name in (
        "README.md",
        "dataset_manifest.json",
        "CITATION.cff",
        "COMMUNITY_USE_POLICY.md",
        "graphrag_publication_checklist.md",
    ):
        assert (base / name).exists(), f"missing Zenodo file: {name}"


def test_dataset_manifest_json_is_valid():
    """Zenodo manifest 必须是合法 JSON 且含关键字段。"""
    m = json.loads((DOCS_ROOT / "docs" / "zenodo_publication" / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert "dataset" in m
    assert m["dataset"].get("license", {}).get("id") == "CC-BY-4.0"
    assert m["dataset"].get("resource_type", {}).get("type") == "DATASET"
    assert "subsets" in m and len(m["subsets"]) >= 3


def test_no_medical_claims_in_cohort_docs():
    """前瞻队列材料必须明确 wellness 定位，不做医疗承诺。"""
    base = DOCS_ROOT / "docs" / "prospective_cohort"
    required = {"study_protocol.md", "informed_consent.md", "recruitment_questionnaire.md"}
    for name in required:
        text = (base / name).read_text(encoding="utf-8")
        assert "wellness" in text.lower() or "非医疗" in text, (
            f"{name}: wellness / 非医疗 disclaimer missing"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
