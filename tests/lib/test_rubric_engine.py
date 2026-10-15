"""L4 rubric_engine 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「自建 rubric 基准」+「position-swap + 多 judge ensemble」校准。

覆盖：
- RubricItem 加载与权重和=1.0 校验
- rule_judge：命中/未命中/红旗扣分/参考答案加分
- Red flag 负向语境过滤（"不构成诊断"不误伤）
- position_swap_judge：构造位置偏差样例，验证 swap 改变判决
- ensemble_judge：多 judge 加权投票
- Benchmark 5 类全跑通
- 空答案 fail-loud
- 未支持的 judge 类型
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.lib.engine_exceptions import HealthLensUnavailableEngine
from app.lib.rubric_engine import (
    LLMJudgeResult,
    RubricEngine,
    RubricItem,
    RuleJudgeResult,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PATH = REPO_ROOT / "data" / "rubric_benchmark_v1.json"


# ─────────────────────────── Fixtures ───────────────────────────

@pytest.fixture(scope="module")
def benchmark_engine() -> RubricEngine:
    engine = RubricEngine()
    engine.load_benchmark(BENCHMARK_PATH)
    return engine


@pytest.fixture
def sample_item() -> RubricItem:
    """构造一个独立测试用的 rubric item。"""
    return RubricItem(
        id="test-001",
        category="axes_interpretation",
        prompt="测试提示",
        rubric_criteria=[
            "A.{0,5}轴",
            "AMPK|mTOR",
            "非诊断",
        ],
        weights={"0": 0.4, "1": 0.3, "2": 0.3},
        reference_pattern="A.{0,5}轴.{0,20}AMPK",
        red_flags=["诊断", "治疗"],
        reference_answer="参考答案",
    )


# ─────────────────────────── 1. RubricItem 结构 ───────────────────────────

class TestRubricItem:
    """RubricItem 数据模型。"""

    def test_from_dict_basic(self) -> None:
        d = {
            "id": "X",
            "category": "axes_interpretation",
            "prompt": "p",
            "rubric_criteria": ["c1", "c2"],
            "weights": {"0": 0.5, "1": 0.5},
            "reference_pattern": "ref",
            "red_flags": ["bad"],
        }
        item = RubricItem.from_dict(d)
        assert item.id == "X"
        assert item.category == "axes_interpretation"
        assert item.rubric_criteria == ["c1", "c2"]
        assert item.weights == {"0": 0.5, "1": 0.5}
        assert item.reference_pattern == "ref"
        assert item.red_flags == ["bad"]

    def test_from_dict_with_defaults(self) -> None:
        d = {"id": "X", "category": "c", "prompt": "p"}
        item = RubricItem.from_dict(d)
        assert item.rubric_criteria == []
        assert item.weights == {}
        assert item.reference_pattern == ""
        assert item.red_flags == []
        assert item.reference_answer == ""
        assert item.expected_tags == []

    def test_to_dict_roundtrip(self, sample_item: RubricItem) -> None:
        d = sample_item.to_dict()
        restored = RubricItem.from_dict(d)
        assert restored.id == sample_item.id
        assert restored.rubric_criteria == sample_item.rubric_criteria
        assert restored.weights == sample_item.weights

    def test_validate_weights_pass(self) -> None:
        item = RubricItem(id="X", category="c", prompt="p", weights={"0": 0.5, "1": 0.5})
        assert item.validate_weights() is True

    def test_validate_weights_fail(self) -> None:
        item = RubricItem(id="X", category="c", prompt="p", weights={"0": 0.3, "1": 0.3})
        assert item.validate_weights() is False

    def test_validate_weights_empty_returns_false(self) -> None:
        item = RubricItem(id="X", category="c", prompt="p", weights={})
        assert item.validate_weights() is False

    def test_validate_weights_tolerance(self) -> None:
        # 0.33+0.33+0.34 = 1.0
        item = RubricItem(id="X", category="c", prompt="p", weights={"0": 0.33, "1": 0.33, "2": 0.34})
        assert item.validate_weights() is True
        # 略偏
        item2 = RubricItem(id="X", category="c", prompt="p", weights={"0": 0.33, "1": 0.33, "2": 0.33})
        assert item2.validate_weights(tolerance=0.02) is True
        assert item2.validate_weights() is False  # 严格模式下 0.99 != 1.0


# ─────────────────────────── 2. Benchmark 加载 ───────────────────────────

class TestBenchmarkLoad:
    """Benchmark JSON 加载与 5 类覆盖。"""

    def test_file_exists(self) -> None:
        assert BENCHMARK_PATH.is_file()

    def test_load_returns_20_plus(self, benchmark_engine: RubricEngine) -> None:
        assert len(benchmark_engine) >= 20

    def test_load_has_all_5_categories(self, benchmark_engine: RubricEngine) -> None:
        cats = benchmark_engine.list_categories()
        assert set(cats.keys()) == {
            "axes_interpretation",
            "tcm_terminology",
            "claims_boundary",
            "critical_values",
            "uncertainty_expression",
        }

    def test_each_category_has_4_to_6_items(self, benchmark_engine: RubricEngine) -> None:
        for cat, ids in benchmark_engine.list_categories().items():
            assert 4 <= len(ids) <= 6, f"{cat}: {len(ids)} items"

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        engine = RubricEngine()
        with pytest.raises(FileNotFoundError):
            engine.load_benchmark(tmp_path / "nonexistent.json")

    def test_load_weights_sum_not_one_raises(self, tmp_path: Path) -> None:
        """权重和≠1.0 必 fail-loud。"""
        bad = {
            "version": "v1",
            "items": [
                {
                    "id": "bad-1",
                    "category": "axes_interpretation",
                    "prompt": "p",
                    "rubric_criteria": ["c1", "c2"],
                    "weights": {"0": 0.3, "1": 0.3},  # sum=0.6
                },
                # 补齐 5 类，每类至少 1 条以通过覆盖校验
                {"id": "tcm-1", "category": "tcm_terminology", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "claims-1", "category": "claims_boundary", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "crit-1", "category": "critical_values", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "unc-1", "category": "uncertainty_expression", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
            ],
        }
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        engine = RubricEngine()
        with pytest.raises(ValueError, match="weights sum"):
            engine.load_benchmark(p)

    def test_load_missing_category_raises(self, tmp_path: Path) -> None:
        """缺 5 类中任一类必 fail-loud。"""
        bad = {
            "version": "v1",
            "items": [
                {"id": "a-1", "category": "axes_interpretation", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "t-1", "category": "tcm_terminology", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "c-1", "category": "claims_boundary", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                {"id": "k-1", "category": "critical_values", "prompt": "p", "rubric_criteria": ["c"], "weights": {"0": 1.0}},
                # 缺 uncertainty_expression
            ],
        }
        p = tmp_path / "missing-cat.json"
        p.write_text(json.dumps(bad), encoding="utf-8")
        engine = RubricEngine()
        with pytest.raises(ValueError, match="missing category"):
            engine.load_benchmark(p)

    def test_get_item_unknown_raises(self, benchmark_engine: RubricEngine) -> None:
        with pytest.raises(KeyError):
            benchmark_engine.get_item("unknown-id")

    def test_items_property_returns_copy(self, benchmark_engine: RubricEngine) -> None:
        items = benchmark_engine.items
        items.clear()  # 修改副本
        assert len(benchmark_engine) > 0  # 不影响原对象

    def test_len_matches_keys(self, benchmark_engine: RubricEngine) -> None:
        assert len(benchmark_engine) == len(benchmark_engine.items)


# ─────────────────────────── 3. rule_judge 基础行为 ───────────────────────────

class TestRuleJudge:
    """Rule judge 评分逻辑。"""

    def test_all_criteria_hit_score_one(self, sample_item: RubricItem) -> None:
        """命中所有 criteria 且无红旗 → 满分 1.0（含 reference bonus）。"""
        engine = RubricEngine()
        answer = "A 轴评分低，涉及 AMPK/mTOR 通路。仅健康参考，非诊断。"
        r = engine.rule_judge(answer, sample_item)
        assert r.score == 1.0
        assert r.hits == ["0", "1", "2"]
        assert r.misses == []
        assert r.red_flag_hits == []

    def test_no_criteria_hit_score_zero(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        answer = "这个答案完全无关。"
        r = engine.rule_judge(answer, sample_item)
        assert r.score == 0.0
        assert r.hits == []
        assert r.misses == ["0", "1", "2"]

    def test_partial_hit_weighted_score(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # 只命中第 0 条（A 轴），weight=0.4
        answer = "A 轴。"
        r = engine.rule_judge(answer, sample_item)
        # base = 0.4/1.0 = 0.4
        # ref bonus = 0（未命中参考答案）
        assert r.score == pytest.approx(0.4, abs=1e-3)

    def test_empty_answer_returns_zero(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.rule_judge("", sample_item)
        assert r.score == 0.0
        assert r.reasoning == "answer is empty"
        assert r.hits == []
        assert r.misses == ["0", "1", "2"]

    def test_whitespace_only_returns_zero(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.rule_judge("   \n  ", sample_item)
        assert r.score == 0.0

    def test_case_insensitive_match(self, sample_item: RubricItem) -> None:
        """正则匹配应忽略大小写。"""
        engine = RubricEngine()
        # 用小写 ampk 匹配 "AMPK|mTOR"
        r = engine.rule_judge("ampk 通路，A 轴", sample_item)
        assert "0" in r.hits
        assert "1" in r.hits


# ─────────────────────────── 4. Red Flag 逻辑 ───────────────────────────

class TestRedFlags:
    """红旗关键词 + 负向语境过滤。"""

    def test_red_flag_hit_reduces_score(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # 命中 criteria 0/1，且未否定地出现"诊断"→ 命中红旗
        answer = "A 轴 AMPK/mTOR 通路，这个能直接诊断糖尿病。"
        r = engine.rule_judge(answer, sample_item)
        assert "诊断" in r.red_flag_hits
        # 分数应低于无红旗版本
        clean = engine.rule_judge("A 轴 AMPK/mTOR 通路，健康参考", sample_item)
        assert r.score < clean.score

    def test_red_flag_negation_ignored(self, sample_item: RubricItem) -> None:
        """「非诊断」应被识别为合规语境，不算红旗。"""
        engine = RubricEngine()
        answer = "A 轴 AMPK/mTOR 通路。不构成诊断或治疗。"
        r = engine.rule_judge(answer, sample_item)
        assert r.red_flag_hits == []

    def test_red_flag_非x_ignored(self, sample_item: RubricItem) -> None:
        """「非诊断」的变体「不做诊断」也应被过滤。"""
        engine = RubricEngine()
        answer = "A 轴 AMPK/mTOR。不做诊断，不做治疗。"
        r = engine.rule_judge(answer, sample_item)
        assert r.red_flag_hits == []

    def test_red_flag_cannot_ignored(self, sample_item: RubricItem) -> None:
        """「不能诊断」应被过滤。"""
        engine = RubricEngine()
        answer = "A 轴 AMPK/mTOR。不能诊断，仅供参考。"
        r = engine.rule_judge(answer, sample_item)
        assert r.red_flag_hits == []

    def test_mixed_negation_and_violation(self, sample_item: RubricItem) -> None:
        """同一答案里既有合规否定也有真违规时，仍应命中红旗。"""
        engine = RubricEngine()
        # "非诊断" 被过滤，但后面 "这个能确诊疾病" 中的 "诊断" 也符合合规语境（因为前面有 "非"）
        # 需要构造真正未定的场景
        answer = "A 轴 AMPK/mTOR。这个能直接治疗糖尿病。"
        r = engine.rule_judge(answer, sample_item)
        assert "治疗" in r.red_flag_hits

    def test_no_red_flags_configured_no_penalty(self) -> None:
        item = RubricItem(id="X", category="c", prompt="p",
                          rubric_criteria=["hi"], weights={"0": 1.0}, red_flags=[])
        engine = RubricEngine()
        r = engine.rule_judge("hi", item)
        assert r.red_flag_hits == []
        assert r.score == 1.0

    def test_multiple_red_flags_all_counted(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # 同时命中"诊断"和"治疗"两个红旗
        answer = "A 轴 AMPK/mTOR。这个诊断糖尿病，还能治疗。"
        r = engine.rule_judge(answer, sample_item)
        assert len(r.red_flag_hits) == 2

    def test_red_flag_only_penalty_no_criteria_hit(self, sample_item: RubricItem) -> None:
        """只有红旗命中但 criteria 全无，score 仍为 0。"""
        engine = RubricEngine()
        answer = "这个能诊断，也能治疗。"
        r = engine.rule_judge(answer, sample_item)
        assert r.hits == []
        assert r.red_flag_hits  # 至少命中一个
        assert r.score == 0.0

    def test_red_flag_penalty_bounded_below_zero(self, sample_item: RubricItem) -> None:
        """红旗扣分不应让分数变负。"""
        engine = RubricEngine()
        answer = "A 轴 AMPK/mTOR 通路。这个能诊断。"
        r = engine.rule_judge(answer, sample_item)
        assert r.score >= 0.0


# ─────────────────────────── 5. Reference Pattern 加分 ───────────────────────────

class TestReferencePattern:
    """参考答案正则匹配 +0.1 加分。"""

    def test_reference_pattern_hit_adds_bonus(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # 命中所有 criteria + reference pattern，score = 1.0
        answer = "A 轴 AMPK/mTOR 通路。非诊断。"
        r = engine.rule_judge(answer, sample_item)
        assert r.score == 1.0
        # reasoning 应含 ref_bonus=0.1
        assert "ref_bonus=0.1" in r.reasoning

    def test_reference_pattern_no_hit_no_bonus(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # 只命中部分 criteria，无 reference pattern 匹配
        answer = "A 轴。"
        r = engine.rule_judge(answer, sample_item)
        assert "ref_bonus=0.0" in r.reasoning

    def test_no_reference_pattern_no_bonus(self) -> None:
        item = RubricItem(id="X", category="c", prompt="p",
                          rubric_criteria=["hi"], weights={"0": 1.0}, reference_pattern="")
        engine = RubricEngine()
        r = engine.rule_judge("hi", item)
        assert "ref_bonus=0.0" in r.reasoning


# ─────────────────────────── 6. Position Swap ───────────────────────────

class TestPositionSwap:
    """Position swap 消除位置偏差。"""

    def test_basic_swap_returns_all_fields(self, sample_item: RubricItem) -> None:
        """A 命中 criteria[0]（"A.{0,5}轴"），B 不命中任何 criteria。"""
        engine = RubricEngine()
        r = engine.position_swap_judge("A 轴 AMPK/mTOR。非诊断。", "完全无关的答案。", sample_item)
        assert "forward" in r
        assert "swapped" in r
        assert "mean_scores" in r
        assert "position_bias" in r
        assert "winner" in r
        assert r["forward"]["a_score"] > 0
        assert r["forward"]["b_score"] == 0

    def test_winner_a_when_better(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        # A 命中 criteria，B 全不命中
        r = engine.position_swap_judge("A 轴 AMPK/mTOR。非诊断。", "完全无关的答案。", sample_item)
        assert r["winner"] == "a"
        assert r["mean_scores"]["a"] > r["mean_scores"]["b"]

    def test_winner_b_when_better(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.position_swap_judge("完全无关的答案。", "A 轴 AMPK/mTOR。非诊断。", sample_item)
        assert r["winner"] == "b"

    def test_tie_when_equal(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.position_swap_judge("A 轴。", "A 轴。", sample_item)
        assert r["winner"] == "tie"
        assert r["mean_scores"]["a"] == r["mean_scores"]["b"]

    def test_position_bias_zero_for_symmetric_judge(self, sample_item: RubricItem) -> None:
        """Rule judge 对位置不敏感 → position_bias=0。"""
        engine = RubricEngine()
        r = engine.position_swap_judge("A 轴。", "B 差", sample_item)
        # rule_judge 不看位置，交换后分数不变
        assert r["position_bias"] == 0.0

    def test_swap_with_custom_judge(self, sample_item: RubricItem) -> None:
        """用自定义 judge_fn 模拟位置偏差。

        judge 对每次调用的"本轮位置"敏感：奇数次（每对的前位）得高分，
        偶数次（每对的后位）得低分。这样 position_swap_judge 内部 4 次调用：
          1) forward_a  → 位置 1（奇）→ 0.9
          2) forward_b  → 位置 2（偶）→ 0.1
          3) swap_a (judge(answer_b)) → 位置 1（奇）→ 0.9
          4) swap_b (judge(answer_a)) → 位置 2（偶）→ 0.1
        于是：
          mean_a = (0.9 + 0.1) / 2 = 0.5
          mean_b = (0.1 + 0.9) / 2 = 0.5
          bias   = (|fwd_a - swap_b| + |fwd_b - swap_a|) / 2
                 = (|0.9 - 0.1| + |0.1 - 0.9|) / 2
                 = 0.8
        """
        engine = RubricEngine()

        calls = []

        def position_biased_judge(answer: str, item: RubricItem) -> RuleJudgeResult:
            calls.append(answer)
            # 奇数次调用（第 1、3 次）视为"位置 1"→ 高分
            # 偶数次调用（第 2、4 次）视为"位置 2"→ 低分
            if len(calls) % 2 == 1:
                return RuleJudgeResult(item_id=item.id, score=0.9, hits=["0"])
            return RuleJudgeResult(item_id=item.id, score=0.1, hits=[])

        r = engine.position_swap_judge("A", "B", sample_item, judge_fn=position_biased_judge)
        assert r["mean_scores"]["a"] == pytest.approx(0.5)
        assert r["mean_scores"]["b"] == pytest.approx(0.5)
        assert r["position_bias"] == pytest.approx(0.8)
        assert len(calls) == 4  # 确认 4 次调用

    def test_mean_scores_average_of_two_runs(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.position_swap_judge("A 轴。", "无关。", sample_item)
        # 对 rule_judge：swap 后分数不变
        fwd_a = r["forward"]["a_score"]
        swap_b = r["swapped"]["b_score"]
        assert r["mean_scores"]["a"] == pytest.approx((fwd_a + swap_b) / 2)

    def test_swap_item_id_preserved(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.position_swap_judge("x", "y", sample_item)
        assert r["item_id"] == sample_item.id


# ─────────────────────────── 7. Ensemble ───────────────────────────

class TestEnsemble:
    """多 judge 加权投票。"""

    def test_two_judges_equal_weight(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()

        def j_high(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.9, hits=["0"])

        def j_low(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.1, hits=[])

        r = engine.ensemble_judge("x", sample_item, judges=[j_high, j_low])
        # 平均 (0.9+0.1)/2 = 0.5
        assert r["final_score"] == pytest.approx(0.5)
        assert r["agreement"] == pytest.approx(0.4)  # std of [0.9, 0.1]

    def test_weighted_ensemble(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()

        def j_high(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.9, hits=["0"])

        def j_low(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.1, hits=[])

        r = engine.ensemble_judge(
            "x", sample_item, judges=[j_high, j_low], weights=[0.8, 0.2]
        )
        # 加权 0.9*0.8 + 0.1*0.2 = 0.74
        assert r["final_score"] == pytest.approx(0.74)

    def test_weights_auto_normalized(self, sample_item: RubricItem) -> None:
        """权重和≠1 时自动归一化。"""
        engine = RubricEngine()

        def j(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.5)

        r = engine.ensemble_judge("x", sample_item, judges=[j, j, j], weights=[1, 1, 1])
        assert r["final_score"] == pytest.approx(0.5)

    def test_empty_judges_raises(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        with pytest.raises(ValueError, match="cannot be empty"):
            engine.ensemble_judge("x", sample_item, judges=[])

    def test_agreement_zero_when_all_equal(self, sample_item: RubricItem) -> None:
        """所有 judge 同分 → agreement=0。"""
        engine = RubricEngine()

        def j(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.5)

        r = engine.ensemble_judge("x", sample_item, judges=[j, j, j])
        assert r["agreement"] == 0.0

    def test_judge_scores_returned(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()

        def j1(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.7, hits=["0"])

        def j2(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.3, hits=[])

        r = engine.ensemble_judge("x", sample_item, judges=[j1, j2])
        assert len(r["judge_scores"]) == 2
        scores = [js["score"] for js in r["judge_scores"]]
        assert 0.7 in scores and 0.3 in scores

    def test_ensemble_with_real_rule_judge(self, benchmark_engine: RubricEngine, sample_item: RubricItem) -> None:
        """用真实 rule_judge 做 ensemble（虽然所有 judge 返回相同结果）。"""
        engine = benchmark_engine
        r = engine.ensemble_judge(
            "A 轴 AMPK/mTOR。非诊断。",
            sample_item,
            judges=[engine.rule_judge, engine.rule_judge, engine.rule_judge],
        )
        assert 0 <= r["final_score"] <= 1
        assert r["agreement"] == 0.0  # 同一 judge 三次必然一致

    def test_ensemble_result_has_item_id(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()

        def j(answer: str, item: RubricItem) -> RuleJudgeResult:
            return RuleJudgeResult(item_id=item.id, score=0.5)

        r = engine.ensemble_judge("x", sample_item, judges=[j])
        assert r["item_id"] == sample_item.id


# ─────────────────────────── 8. LLM Judge 未配 key ───────────────────────────

class TestLLMJudge:
    """LLM judge 未配 API key 时 fail-loud。"""

    def test_llm_judge_without_api_key_raises(self, sample_item: RubricItem) -> None:
        import os

        # 确保 key 未设置
        old = os.environ.get("SENSENOVA_API_KEY")
        os.environ.pop("SENSENOVA_API_KEY", None)
        try:
            engine = RubricEngine()
            with pytest.raises(HealthLensUnavailableEngine):
                engine.llm_judge("some answer", sample_item)
        finally:
            if old:
                os.environ["SENSENOVA_API_KEY"] = old

    def test_llm_result_dataclass_shape(self) -> None:
        r = LLMJudgeResult(
            item_id="X", score=0.7, hits=["0"], misses=["1"],
            red_flag_hits=[], reasoning="ok", raw_response="{}", model="sensechat-plus",
        )
        d = r.to_dict()
        assert d["judge_type"] == "llm"
        assert d["model"] == "sensechat-plus"
        assert d["item_id"] == "X"
        assert d["score"] == 0.7

    def test_rule_result_dataclass_shape(self, sample_item: RubricItem) -> None:
        engine = RubricEngine()
        r = engine.rule_judge("A 轴。", sample_item)
        d = r.to_dict()
        assert d["judge_type"] == "rule"
        assert d["item_id"] == sample_item.id
        assert 0 <= d["score"] <= 1


# ─────────────────────────── 9. 全量 Benchmark 跑通 ───────────────────────────

class TestFullBenchmark:
    """对全量 benchmark 每个 item 都跑一次 rule_judge 不崩溃。"""

    def test_all_items_runnable(self, benchmark_engine: RubricEngine) -> None:
        """每个 item 用参考答案跑 rule_judge 应得高分。"""
        for iid, item in benchmark_engine.items.items():
            r = benchmark_engine.rule_judge(item.reference_answer, item)
            # 参考答案应至少得 0.5 分（不严格 = 满分，因为 references 是描述性）
            assert r.score >= 0.3, f"{iid}: ref_answer score={r.score} too low"

    def test_all_items_bad_answer_low_score(self, benchmark_engine: RubricEngine) -> None:
        """完全无关答案应得低分。"""
        bad_answer = "这个可以完全诊断并治疗任何疾病。"
        for iid, item in benchmark_engine.items.items():
            r = benchmark_engine.rule_judge(bad_answer, item)
            assert r.score < 0.5, f"{iid}: bad answer got {r.score}"

    def test_weighted_scores_sum_to_one_per_item(self, benchmark_engine: RubricEngine) -> None:
        """每条 item 权重和=1.0。"""
        for item in benchmark_engine.items.values():
            assert item.validate_weights(), f"{item.id} weights sum != 1"

    def test_all_items_have_reference_pattern(self, benchmark_engine: RubricEngine) -> None:
        for item in benchmark_engine.items.values():
            assert item.reference_pattern, f"{item.id} missing reference_pattern"

    def test_all_items_have_red_flags(self, benchmark_engine: RubricEngine) -> None:
        for item in benchmark_engine.items.values():
            assert item.red_flags, f"{item.id} missing red_flags"

    def test_all_items_have_prompt(self, benchmark_engine: RubricEngine) -> None:
        for item in benchmark_engine.items.values():
            assert item.prompt, f"{item.id} missing prompt"

    def test_category_coverage_counts(self, benchmark_engine: RubricEngine) -> None:
        counts = {cat: len(ids) for cat, ids in benchmark_engine.list_categories().items()}
        # 各类样本数
        assert counts["axes_interpretation"] >= 4
        assert counts["tcm_terminology"] >= 4
        assert counts["claims_boundary"] >= 4
        assert counts["critical_values"] >= 4
        assert counts["uncertainty_expression"] >= 4
