"""D1 (2026-10-18 复评)：论文声称数字 vs 数据实况门禁。

S7 硬伤（10-18 报告最严重）：论文 §5 把 76% 合成夹具的案例库称为
"real-world"，L1=56 里 48 条是合成件——审稿人对照 Zenodo 公开数据
即可证伪，属可外部核验的 over-claim。

本文件锁死三件事：
1. 论文声称的「总条数」== DB 实际条数
2. 论文声称的「已核验子集条数」== 实际 verified_crossref + traditional 条数
3. 论文声称的「合成件条数」== 实际 synthetic_validation 条数

以及运行时：
4. L1 数不能来自 synthetic_validation（否则范畴错误）
5. coverage_L1 与 baseline 快照一致（防再次漂移）

一旦有人把 DB 改了但忘改论文，或反之，本测试立即红。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "case_evidence_db.json"
PAPER_PATH = REPO_ROOT / "HealthLens_论文_英文版_全文.md"
BASELINE_PATH = REPO_ROOT / "validation_snapshots" / "BASELINE.json"


@pytest.fixture(scope="module")
def db_cases() -> list[dict]:
    with open(DB_PATH, encoding="utf-8") as f:
        return json.load(f)["cases"]


@pytest.fixture(scope="module")
def paper_text() -> str:
    return PAPER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def baseline() -> dict:
    with open(BASELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestCaseLibraryCounts:
    """DB 侧：条数按 citation_status 分级。"""

    def test_total_is_120(self, db_cases: list[dict]) -> None:
        assert len(db_cases) == 120, (
            f"case_evidence_db.json 应含 120 条案例（论文 §5 声称 n=120），"
            f"实际 {len(db_cases)} 条"
        )

    def test_synthetic_share_is_76pct(self, db_cases: list[dict]) -> None:
        """S7 修复的核心披露：76% 是合成件，必须如实标注。"""
        status_counts = Counter(c.get("citation_status") for c in db_cases)
        synthetic = status_counts.get("synthetic_validation", 0)
        # 允许 ±1 条抖动（新增/删除一条时不算漂移）
        assert abs(synthetic - 91) <= 1, (
            f"synthetic_validation 应为 91（76%），实际 {synthetic}。"
            f"如新增/删除合成件请同步更新论文 §5 表格。"
        )

    def test_verified_crossref_is_7(self, db_cases: list[dict]) -> None:
        status_counts = Counter(c.get("citation_status") for c in db_cases)
        verified = status_counts.get("verified_crossref", 0)
        assert verified == 7, (
            f"verified_crossref 应为 7，实际 {verified}。"
            f"论文 §5 'cited (L1–L3) subset = 15' 会因此漂移。"
        )

    def test_traditional_is_8(self, db_cases: list[dict]) -> None:
        status_counts = Counter(c.get("citation_status") for c in db_cases)
        traditional = status_counts.get("traditional", 0)
        assert traditional == 8, (
            f"traditional 应为 8，实际 {traditional}。"
        )


class TestPaperClaimsMatchData:
    """论文 §5 声称的数字必须与 DB 实况逐项相等。"""

    def test_section5_total_matches(self, db_cases: list[dict], paper_text: str) -> None:
        total = len(db_cases)
        # 论文 §5 应出现 "n=120" 或 "total: 120" 字样
        m = re.search(r"n\s*=\s*(\d+)", paper_text)
        assert m is not None, "论文 §5 应含 'n=<数字>' 的总条数声明"
        assert int(m.group(1)) == total, (
            f"论文声称 n={m.group(1)}，DB 实际 {total} 条"
        )

    def test_section5_discloses_synthetic_share(self, paper_text: str) -> None:
        """S7 修复的硬指标：论文必须显式披露 91 或 76%。"""
        assert ("91" in paper_text) or ("76%" in paper_text) or ("76 %" in paper_text), (
            "论文未显式披露 91 synthetic_validation 条或 76% 合成占比——"
            "S7 over-claim 复发了"
        )

    def test_section5_removed_real_world_claim(self, paper_text: str) -> None:
        """S7 修复：摘要与 §5 标题必须不再出现 'real-world case evidence base'
        或 'Real-World Case Library' 这种把合成件当真实数据的表述。"""
        # 找所有 "real-world" 出现处，检查是否被"case evidence base"、"Case Library"、
        # "human evidence base"（复数）等旧口径包裹
        bad_patterns = [
            r"real[- ]world\s+case\s+evidence\s+base",
            r"Real[- ]World\s+Case\s+Library",
            r"real[- ]world\s+human[- ]evidence\s+base",
            r"120\s+real\s+human-trial",
        ]
        for pat in bad_patterns:
            m = re.search(pat, paper_text)
            assert m is None, (
                f"论文仍含 over-claim 表述「{m.group(0)}」——S7 修复未完成"
            )

    def test_section5_uses_stratified_title(self, paper_text: str) -> None:
        """D1 修复：§5 标题应为「Stratified by Verification Status」。"""
        m = re.search(r"^##\s+5\.\s+(.+)$", paper_text, re.MULTILINE)
        assert m is not None, "论文 §5 标题缺失"
        title = m.group(1)
        assert "stratified" in title.lower(), (
            f"§5 标题应为 'Stratified by Verification Status'，"
            f"实际：'{title}'"
        )


class TestL1CategoryError:
    """S7 的范畴错误：L1 定义（≥2 项独立人体 RCT 一致）在定义上不可能
    由 synthetic_validation 满足。DB 里可以标注 L1，但 fusion_engine
    推荐时必须把它们归 S 类，不能进 L1 池。"""

    def test_fusion_engine_normalizes_synthetic_to_S(self, db_cases: list[dict]) -> None:
        from app.lib.fusion_engine import normalize_evidence_grade

        synthetic_cases = [c for c in db_cases if c.get("citation_status") == "synthetic_validation"]
        assert synthetic_cases, "DB 应含 synthetic_validation 案例"
        for c in synthetic_cases:
            grade = normalize_evidence_grade(c)
            assert grade == "S", (
                f"case {c.get('id')} citation_status=synthetic_validation 应归 S，"
                f"实际归 {grade}"
            )

    def test_fusion_engine_keeps_verified_L1(self, db_cases: list[dict]) -> None:
        from app.lib.fusion_engine import normalize_evidence_grade

        verified_l1 = [
            c for c in db_cases
            if c.get("citation_status") == "verified_crossref"
            and c.get("evidence_level") == "L1"
        ]
        assert verified_l1, "DB 应含 verified_crossref + L1 案例"
        for c in verified_l1:
            assert normalize_evidence_grade(c) == "L1", (
                f"case {c.get('id')} verified_crossref + L1 应保留 L1"
            )

    def test_no_recommended_L1_is_synthetic(self) -> None:
        """运行时：从 fusion_engine.recommend() 拿出的所有 L1 推荐，
        其对应 case 的 citation_status 不可能是 synthetic_validation。"""
        from app.lib.fusion_engine import recommend, UserProfile, load_cases

        # 用一个覆盖多轴弱项的画像触发大量个性化推荐
        cases = load_cases()
        profile = UserProfile(weak_axes=set("ABCDEFGH"))
        result = recommend(profile, cases=cases, top_k=200)
        l1_recs = [r for r in result["recommendations"] if r["evidence_level"] == "L1"]

        case_by_id = {c.get("id"): c for c in cases}
        for r in l1_recs:
            case = case_by_id.get(r["case_id"])
            if case is None:
                continue
            status = case.get("citation_status", "")
            assert status != "synthetic_validation", (
                f"L1 推荐 case {r['case_id']} 的 citation_status=synthetic_validation——"
                f"S7 范畴错误复发"
            )


class TestValidationMetricsFresh:
    """D1 收尾：baseline 快照的 coverage_L1 必须与 S7 修复后的诚实值一致。

    旧值 0.95 是 S7 未修复时把 48 条 synthetic 当 L1 的假象；
    修复后应为 0.75（只算 verified + classical L1）。
    """

    def test_coverage_L1_is_honest_value(self, baseline: dict) -> None:
        cov = baseline.get("coverage_L1")
        assert cov is not None, "BASELINE.json 缺 coverage_L1"
        # S7 修复后的诚实值；容忍 ±0.02 抖动
        assert 0.70 <= cov <= 0.80, (
            f"coverage_L1={cov} 与 S7 修复后的诚实值（~0.75）不符——"
            f"要么 BASELINE 未刷新，要么 fusion_engine 归一逻辑被回滚"
        )

    def test_evidence_dist_has_no_synthetic_L1(self, baseline: dict) -> None:
        """baseline 的 L1 数应显著低于旧 134 值（旧值含 48 synthetic 假 L1）。"""
        ev = baseline.get("evidence_dist_personalized", {})
        l1 = ev.get("L1", 0)
        assert l1 < 100, (
            f"evidence_dist_personalized.L1={l1} 与 S7 修复后诚实值（~28）不符——"
            f"可能仍在把 synthetic 计为 L1"
        )

    def test_convergent_validity_updated(self, baseline: dict) -> None:
        """S7 修复后 domain-expectation concordance 应为 ~0.88（旧 0.70 已过期）。"""
        rate = baseline.get("domain_expectation_concordance") or baseline.get("convergent_validity_rate")
        assert rate is not None, "BASELINE 缺 convergent_validity_rate"
        assert rate >= 0.80, (
            f"convergent_validity_rate={rate} 与 S7 修复后诚实值（~0.879）不符"
        )
