"""Rubric 评估引擎 —— L4 评估闭环

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「自建 rubric 基准」+「Judge 偏差校准：position-swap + 多 judge ensemble」。

定位：
- **确定性规则 judge 优先**：`rule_judge` 用纯正则 + 关键词匹配，可完全离线跑，
  CI 无 LLM 也能验证 rubric 结构正确性。
- **可选 LLM judge**：`llm_judge` 走 SenseNova（`https://token.sensenova.cn/v1`），
  未配 API key 时抛 `HealthLensUnavailableEngine`，fail-loud 不静默降级。
- **Position-swap**：`position_swap_judge` 交换 A/B 位置各跑一次，消除位置偏差。
- **Ensemble**：`ensemble_judge` 支持多个 judge 加权投票，减少单 judge 偏差。

Wellness 平台术语纪律：本模块只评估健康/关注/引导类输出，不做诊断/治疗建议。

作者：HealthLens L4 评估团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from app.lib.engine_exceptions import HealthLensUnavailableEngine


# ─────────────────────────── 数据结构 ───────────────────────────

@dataclass(frozen=True)
class RubricItem:
    """单条 rubric 项（对应 benchmark 中一条样本）。

    Attributes:
        id: 唯一 id（如 "axes-A-001"）
        category: 类别（axes_interpretation / tcm_terminology / claims_boundary /
                  critical_values / uncertainty_expression）
        prompt: 输入提示词（会喂给被测 LLM）
        rubric_criteria: 判据列表（每条为一个正则或短语）
        weights: 每个判据的权重（键为 rubric_criteria 的下标字符串），总和=1.0
        reference_pattern: 参考答案的正则（供 rule_judge 做相似匹配）
        red_flags: 红旗关键词（命中即失分）
        reference_answer: 参考答案（可选，用于对比）
        expected_tags: 预期命中的标签集合（可选，辅助评估）
    """

    id: str
    category: str
    prompt: str
    rubric_criteria: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    reference_pattern: str = ""
    red_flags: list[str] = field(default_factory=list)
    reference_answer: str = ""
    expected_tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RubricItem":
        return cls(
            id=str(d["id"]),
            category=str(d["category"]),
            prompt=str(d.get("prompt", "")),
            rubric_criteria=[str(x) for x in d.get("rubric_criteria", [])],
            weights={str(k): float(v) for k, v in d.get("weights", {}).items()},
            reference_pattern=str(d.get("reference_pattern", "")),
            red_flags=[str(x) for x in d.get("red_flags", [])],
            reference_answer=str(d.get("reference_answer", "")),
            expected_tags=[str(x) for x in d.get("expected_tags", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "prompt": self.prompt,
            "rubric_criteria": self.rubric_criteria,
            "weights": self.weights,
            "reference_pattern": self.reference_pattern,
            "red_flags": self.red_flags,
            "reference_answer": self.reference_answer,
            "expected_tags": self.expected_tags,
        }

    def validate_weights(self, tolerance: float = 1e-6) -> bool:
        """权重和必须为 1.0（±tolerance）。"""
        return abs(sum(self.weights.values()) - 1.0) <= tolerance


@dataclass
class RuleJudgeResult:
    """规则 judge 的输出。"""

    item_id: str
    score: float  # [0, 1]
    hits: list[str] = field(default_factory=list)  # 命中的 criteria id
    misses: list[str] = field(default_factory=list)  # 未命中
    red_flag_hits: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "score": self.score,
            "hits": self.hits,
            "misses": self.misses,
            "red_flag_hits": self.red_flag_hits,
            "reasoning": self.reasoning,
            "judge_type": "rule",
        }


@dataclass
class LLMJudgeResult:
    """LLM judge 的输出。"""

    item_id: str
    score: float
    hits: list[str] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    red_flag_hits: list[str] = field(default_factory=list)
    reasoning: str = ""
    raw_response: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "score": self.score,
            "hits": self.hits,
            "misses": self.misses,
            "red_flag_hits": self.red_flag_hits,
            "reasoning": self.reasoning,
            "model": self.model,
            "judge_type": "llm",
        }


# ─────────────────────────── Judge 抽象 ───────────────────────────

class Judge(Protocol):
    """Judge 协议。"""

    def judge(self, answer: str, item: RubricItem) -> RuleJudgeResult | LLMJudgeResult: ...


# ─────────────────────────── RubricEngine ───────────────────────────

class RubricEngine:
    """Rubric 评估引擎。

    用法：
        engine = RubricEngine()
        engine.load_benchmark("data/rubric_benchmark_v1.json")
        result = engine.rule_judge(answer, engine.get_item("axes-A-001"))
    """

    CATEGORIES = (
        "axes_interpretation",
        "tcm_terminology",
        "claims_boundary",
        "critical_values",
        "uncertainty_expression",
    )

    def __init__(self) -> None:
        self._items: dict[str, RubricItem] = {}
        self._by_category: dict[str, list[str]] = {}

    @property
    def items(self) -> dict[str, RubricItem]:
        return dict(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def get_item(self, item_id: str) -> RubricItem:
        if item_id not in self._items:
            raise KeyError(f"rubric item {item_id!r} not found")
        return self._items[item_id]

    def list_categories(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._by_category.items()}

    def load_benchmark(self, path: str | Path) -> int:
        """加载 benchmark JSON 文件。

        文件格式：
        {
            "version": "v1",
            "items": [ {RubricItem.to_dict()}, ... ]
        }

        Returns:
            加载的 item 数量
        """
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"benchmark not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", [])
        if not isinstance(items, list):
            raise ValueError("benchmark items must be a list")
        self._items.clear()
        self._by_category.clear()
        for d in items:
            item = RubricItem.from_dict(d)
            # 权重和校验（fail-loud）
            if not item.validate_weights():
                total = sum(item.weights.values())
                raise ValueError(
                    f"rubric item {item.id!r} weights sum={total:.4f}, expected 1.0"
                )
            self._items[item.id] = item
            self._by_category.setdefault(item.category, []).append(item.id)
        # 校验类别覆盖
        for cat in self.CATEGORIES:
            if cat not in self._by_category:
                raise ValueError(
                    f"benchmark missing category {cat!r}; must cover all 5 categories"
                )
        return len(self._items)

    # ─────────────────────────── 规则 judge ───────────────────────────

    @staticmethod
    def _criteria_matches(answer: str, pattern: str) -> bool:
        """尝试把 pattern 当正则匹配；失败时降级为子串匹配。"""
        if not pattern:
            return False
        try:
            return re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            # pattern 非法正则，视为字面串
            return pattern.lower() in answer.lower()

    @staticmethod
    def _red_flag_hits(answer: str, red_flags: list[str]) -> list[str]:
        """扫描 red flag 命中。

        **负向语境过滤**：如果 red flag 前 8 字符内出现否定/合规前缀
        （如「非诊断」「不构成治疗」「不能治愈」「勿」「请勿」「避免」「不宣称」），
        则**不算**命中——因为这类表述本身就是合规的边界声明，
        不应被当作违规。避免参考答案"不构成诊断"被"诊断" red flag 误伤。

        实现：对每个 red_flag，取其在 answer 中每次出现位置的上下文窗口
        [max(0, idx-10) : idx]，若窗口含任一负向前缀则跳过该次出现。
        """
        hits: list[str] = []
        low_answer = answer.lower()
        # 负向/合规前缀（中文 + 常见英文短语）
        _NEG_PREFIXES = (
            "非诊断", "不构成", "不能", "未实现", "不做", "不做诊断",
            "不宣称", "非治疗", "非药物", "非医疗", "仅供参考",
            "not diagnosis", "not treatment", "not medical", "not therapeutic",
            "no diagnosis", "no treatment", "not treat", "does not treat",
            "非", "不含", "不涉及", "不构成",
            "勿", "请勿", "避免", "禁止", "should not", "must not",
            "not ", "cannot", "not_",
        )
        for rf in red_flags:
            if not rf:
                continue
            idx = 0
            matched_with_context = False
            while True:
                pos = low_answer.find(rf.lower(), idx)
                if pos < 0:
                    break
                ctx = low_answer[max(0, pos - 12) : pos]
                if any(p in ctx for p in _NEG_PREFIXES):
                    # 该次出现属合规语境，跳过
                    idx = pos + len(rf)
                    continue
                matched_with_context = True
                idx = pos + len(rf)
            if matched_with_context:
                hits.append(rf)
        return hits

    def rule_judge(self, answer: str, item: RubricItem) -> RuleJudgeResult:
        """纯正则 + 关键词匹配评分。

        评分公式：
            base_score = Σ(weight_i × hit_i) / Σ(weight_i)
            red_flag_penalty = 0.5 × (命中红旗数 / 总红旗数) 或 0.5 若命中至少一个
            final_score = max(0, base_score - red_flag_penalty)
        """
        if not isinstance(answer, str) or not answer.strip():
            return RuleJudgeResult(
                item_id=item.id,
                score=0.0,
                hits=[],
                misses=[str(i) for i in range(len(item.rubric_criteria))],
                red_flag_hits=self._red_flag_hits(answer or "", item.red_flags),
                reasoning="answer is empty",
            )

        hits: list[str] = []
        misses: list[str] = []
        weighted_hit = 0.0
        total_weight = 0.0

        for i, criteria in enumerate(item.rubric_criteria):
            key = str(i)
            w = item.weights.get(key, 0.0)
            total_weight += w
            if self._criteria_matches(answer, criteria):
                hits.append(key)
                weighted_hit += w
            else:
                misses.append(key)

        base_score = weighted_hit / total_weight if total_weight > 0 else 0.0

        rf_hits = self._red_flag_hits(answer, item.red_flags)
        if rf_hits:
            # 命中红旗：直接扣一半基础分（保底非负）
            red_penalty = 0.5 * min(1.0, len(rf_hits) / max(1, len(item.red_flags)))
            final_score = max(0.0, base_score - red_penalty)
        else:
            final_score = base_score

        # 参考答案正则匹配（若提供）——加分（最多 +0.1），但不会超过 1.0
        ref_bonus = 0.0
        if item.reference_pattern:
            if self._criteria_matches(answer, item.reference_pattern):
                ref_bonus = 0.1
        final_score = min(1.0, final_score + ref_bonus)

        return RuleJudgeResult(
            item_id=item.id,
            score=round(final_score, 4),
            hits=hits,
            misses=misses,
            red_flag_hits=rf_hits,
            reasoning=(
                f"base={base_score:.3f} weighted_hits={weighted_hit:.3f}/"
                f"{total_weight:.3f} ref_bonus={ref_bonus:.3f} "
                f"red_flags={len(rf_hits)}/{len(item.red_flags)}"
            ),
        )

    # ─────────────────────────── LLM judge（可选） ───────────────────────────

    LLM_BASE_URL = "https://token.sensenova.cn/v1"

    def llm_judge(
        self,
        answer: str,
        item: RubricItem,
        *,
        api_key: str | None = None,
        model: str = "sensechat-plus",
        base_url: str | None = None,
    ) -> LLMJudgeResult:
        """用 LLM 做 judge。未配 API key 时抛 HealthLensUnavailableEngine。

        SenseNova LLM endpoint: POST https://token.sensenova.cn/v1/chat/completions
        """
        api_key = api_key or os.environ.get("SENSENOVA_API_KEY") or os.environ.get("SENSE_OPENAI_API_KEY")
        if not api_key:
            raise HealthLensUnavailableEngine(
                engine_name="sensenova-llm",
                required_package="SENSENOVA_API_KEY env var",
                detail="Set SENSENOVA_API_KEY to enable LLM judge.",
            )
        import httpx  # noqa: F401  已在 pyproject

        base = base_url or self.LLM_BASE_URL
        rubric_list = "\n".join(
            f"- [{i}] (weight={item.weights.get(str(i), 0):.2f}) {c}"
            for i, c in enumerate(item.rubric_criteria)
        )
        red_flag_list = "\n".join(f"- {rf}" for rf in item.red_flags) if item.red_flags else "(none)"
        system_prompt = (
            "You are a strict rubric judge for a wellness platform. "
            "You must NOT treat outputs as medical advice or diagnosis. "
            "Score based ONLY on the rubric provided. "
            "Respond in STRICT JSON: {\"score\": float 0-1, \"hits\": [int indices], "
            "\"misses\": [int indices], \"red_flag_hits\": [str], \"reasoning\": str}. "
            "No markdown, no prose outside JSON."
        )
        user_prompt = (
            f"### PROMPT\n{item.prompt}\n\n"
            f"### ANSWER TO JUDGE\n{answer}\n\n"
            f"### RUBRIC CRITERIA (index: criterion)\n{rubric_list}\n\n"
            f"### RED FLAGS (must NOT appear in answer)\n{red_flag_list}\n\n"
            f"### REFERENCE PATTERN\n{item.reference_pattern or '(none)'}\n\n"
            "Return JSON only."
        )
        try:
            resp = httpx.post(
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise HealthLensUnavailableEngine(
                engine_name="sensenova-llm",
                required_package="sensenova API reachable",
                detail=f"LLM judge call failed: {type(exc).__name__}: {exc}",
            ) from exc

        # 解析 LLM 输出
        try:
            obj = self._extract_json_object(raw)
        except ValueError:
            # LLM 输出不合法 → fail-loud
            return LLMJudgeResult(
                item_id=item.id,
                score=0.0,
                hits=[],
                misses=[str(i) for i in range(len(item.rubric_criteria))],
                reasoning=f"LLM returned non-JSON: {raw[:200]}",
                raw_response=raw,
                model=model,
            )
        return LLMJudgeResult(
            item_id=item.id,
            score=float(obj.get("score", 0.0)),
            hits=[str(x) for x in obj.get("hits", [])],
            misses=[str(x) for x in obj.get("misses", [])],
            red_flag_hits=[str(x) for x in obj.get("red_flag_hits", [])],
            reasoning=str(obj.get("reasoning", "")),
            raw_response=raw,
            model=model,
        )

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        """从 LLM 文本中提取 JSON object（容错 markdown 围栏）。"""
        text = text.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
        # 尝试直接 parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试找第一个 {}
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError as exc:
                raise ValueError(f"LLM output not valid JSON: {exc}") from exc
        raise ValueError("LLM output contains no JSON object")

    # ─────────────────────────── Position swap ───────────────────────────

    def position_swap_judge(
        self,
        answer_a: str,
        answer_b: str,
        item: RubricItem,
        judge_fn: Callable[[str, RubricItem], RuleJudgeResult | LLMJudgeResult] | None = None,
    ) -> dict[str, Any]:
        """交换 A/B 位置各 judge 一次，消除位置偏差。

        用于比较「同一 prompt 的两个答案」时避免 LLM judge 偏爱先出现的。

        Args:
            answer_a, answer_b: 两个答案
            item: rubric 项
            judge_fn: 可复用的 judge 函数（默认使用 rule_judge）

        Returns:
            {
                "forward": {"a_score":..., "b_score":...},
                "swapped": {"a_score":..., "b_score":...},
                "mean_scores": {"a": ..., "b": ...},
                "position_bias": float  # |a_fwd - a_swap| + |b_fwd - b_swap| / 2
                "winner": "a" | "b" | "tie"
            }
        """
        if judge_fn is None:
            judge_fn = self.rule_judge

        fwd_a = judge_fn(answer_a, item).score
        fwd_b = judge_fn(answer_b, item).score
        # swapped：把 b 当 a 位置、a 当 b 位置
        swap_a = judge_fn(answer_b, item).score
        swap_b = judge_fn(answer_a, item).score

        mean_a = (fwd_a + swap_b) / 2
        mean_b = (fwd_b + swap_a) / 2
        bias = (abs(fwd_a - swap_b) + abs(fwd_b - swap_a)) / 2

        if abs(mean_a - mean_b) < 1e-6:
            winner = "tie"
        elif mean_a > mean_b:
            winner = "a"
        else:
            winner = "b"

        return {
            "item_id": item.id,
            "forward": {"a_score": fwd_a, "b_score": fwd_b},
            "swapped": {"a_score": swap_a, "b_score": swap_b},
            "mean_scores": {"a": mean_a, "b": mean_b},
            "position_bias": bias,
            "winner": winner,
        }

    # ─────────────────────────── Ensemble ───────────────────────────

    def ensemble_judge(
        self,
        answer: str,
        item: RubricItem,
        judges: list[Callable[[str, RubricItem], RuleJudgeResult | LLMJudgeResult]],
        weights: list[float] | None = None,
    ) -> dict[str, Any]:
        """多 judge 加权投票。

        Args:
            judges: judge 函数列表
            weights: 每个 judge 的权重（不传则等权）

        Returns:
            {
                "item_id": str,
                "final_score": float,
                "judge_scores": [{"name": ..., "score": ..., "weight": ...}, ...],
                "agreement": float  # 分数标准差，越大越分歧
            }
        """
        if not judges:
            raise ValueError("judges list cannot be empty")
        if weights is None:
            weights = [1.0 / len(judges)] * len(judges)
        total_w = sum(weights)
        if abs(total_w - 1.0) > 1e-6:
            weights = [w / total_w for w in weights]

        results = []
        scores: list[float] = []
        weighted_sum = 0.0
        for judge_fn, w in zip(judges, weights):
            r = judge_fn(answer, item)
            s = r.score
            weighted_sum += w * s
            scores.append(s)
            results.append({
                "score": s,
                "weight": w,
                "judge_type": getattr(r, "judge_type", "unknown"),
            })
        # 分歧度（标准差）
        n = len(scores)
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / n if n else 0.0
        agreement = variance ** 0.5

        return {
            "item_id": item.id,
            "final_score": round(weighted_sum, 4),
            "judge_scores": results,
            "agreement": round(agreement, 4),
        }
