"""RAGAS faithfulness Adapter —— L4 评估层

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「GraphRAG 幻觉评测：RAGAS faithfulness（2026 最成熟通用框架）」。

定位：
- **薄 Adapter**：只暴露 `faithfulness_check(answer, context)`，其他 RAGAS
  metric（context_recall / context_precision / answer_relevancy）留待后续。
- **未装即 fail-loud**：无 RAGAS 时抛 `HealthLensUnavailableEngine`，
  让上层明确告知用户 `pip install -e '.[evaluation]'`。
- **纯 Python fallback**：`fallback_faithfulness` 用简单 N-gram overlap
  近似 faithfulness（保守估计，作为 baseline 对比，不当作真值）。

Wellness 平台术语纪律：本模块只评估答案是否忠于给定 context，不做业务判断。

作者：HealthLens L4 评估团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import importlib.util
import re
from typing import Any

from app.lib.engine_exceptions import HealthLensUnavailableEngine


_ENGINE_NAME = "ragas"
_REQUIRED_PACKAGE = "ragas"
_EXTRA_HINT = "evaluation"


def _ragas_available() -> bool:
    return importlib.util.find_spec("ragas") is not None


def _require_ragas():
    if not _ragas_available():
        raise HealthLensUnavailableEngine(
            engine_name=_ENGINE_NAME,
            required_package=_REQUIRED_PACKAGE,
            extra_hint=_EXTRA_HINT,
            detail="pip install -e '.[evaluation]' 以安装 ragas>=0.3",
        )
    import ragas  # type: ignore[import-not-found]

    return ragas


def probe() -> dict[str, Any]:
    """探测 RAGAS 是否可用（供 API /probe 端点使用）。"""
    avail = _ragas_available()
    version = None
    if avail:
        try:
            import ragas  # type: ignore[import-not-found]

            version = getattr(ragas, "__version__", None)
        except Exception:  # noqa: BLE001
            version = None
    return {
        "engine": _ENGINE_NAME,
        "available": avail,
        "version": version,
        "install_hint": "pip install -e '.[evaluation]'",
        "note": (
            "RAGAS 已装，可运行 faithfulness_check"
            if avail
            else "RAGAS 未装，faithfulness_check 将抛 HealthLensUnavailableEngine；"
            "可用 fallback_faithfulness 做粗略 baseline"
        ),
    }


def faithfulness_check(answer: str, context: str, **kwargs: Any) -> float:
    """用 RAGAS faithfulness metric 评分答案是否忠于 context。

    报告定位（§5 L4）：RAGAS faithfulness 是当前最成熟的通用幻觉评测框架。

    Args:
        answer: 待评估的答案文本
        context: 事实来源（RAGAS 要求非空字符串；空 context 会返回 0.0）
        **kwargs: 透传给 RAGAS 的额外参数（如 embeddings、llm 覆盖）

    Returns:
        0.0 - 1.0 的 faithfulness 分数

    Raises:
        HealthLensUnavailableEngine: ragas 未安装或调用失败
        ValueError: answer 或 context 类型错误
    """
    _require_ragas()
    if not isinstance(answer, str):
        raise ValueError(f"answer must be str, got {type(answer).__name__}")
    if not isinstance(context, str):
        raise ValueError(f"context must be str, got {type(context).__name__}")
    if not answer.strip():
        return 0.0
    if not context.strip():
        # 无 context 无法判断忠告性，返回 0.0 而非抛错
        return 0.0

    try:
        from ragas.metrics import Faithfulness  # type: ignore[import-not-found]

        metric = Faithfulness(**kwargs)
        result = metric.single_turn_ascore(answer=answer, contexts=[context])
        # ragas 各版本返回类型不一：单值 / dict / AsyncScore
        if isinstance(result, dict):
            # 常见 key: "faithfulness" 或 "score"
            for k in ("faithfulness", "score", "value"):
                if k in result:
                    return float(result[k])
            # 兜底：取第一个 float
            for v in result.values():
                if isinstance(v, (int, float)):
                    return float(v)
            return 0.0
        return float(result)
    except HealthLensUnavailableEngine:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HealthLensUnavailableEngine(
            engine_name=_ENGINE_NAME,
            required_package=_REQUIRED_PACKAGE,
            detail=f"faithfulness_check failed: {type(exc).__name__}: {exc}",
        ) from exc


# ─────────────────────────── Fallback（纯 Python baseline） ───────────────────────────

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _ngrams(text: str, n: int = 3) -> set[tuple[str, ...]]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _token_set(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def fallback_faithfulness(answer: str, context: str) -> float:
    """Fallback faithfulness：用 token / 3-gram overlap 粗略估计。

    **注意**：这不是真 faithfulness——它只能作为 baseline 对比。真正的
    faithfulness 需要 LLM 判断「答案的每个陈述是否能在 context 中找到依据」。
    本 fallback 只用于：
    1. CI 无 ragas 时冒烟测试不崩溃
    2. 快速对比 RAGAS 真值与 baseline 差异

    算法：
        token_precision = |answer_tokens ∩ context_tokens| / |answer_tokens|
        ngram_precision = |answer_ngrams ∩ context_ngrams| / |answer_ngrams|
        return 0.6 × token_precision + 0.4 × ngram_precision

    分数范围 [0, 1]。answer 空 → 0.0；context 空 → 0.0；answer 完全匹配 → ~1.0。
    """
    if not isinstance(answer, str) or not isinstance(context, str):
        raise ValueError("answer and context must be str")
    if not answer.strip() or not context.strip():
        return 0.0

    a_tokens = _token_set(answer)
    c_tokens = _token_set(context)
    if not a_tokens:
        return 0.0
    token_p = len(a_tokens & c_tokens) / len(a_tokens)

    a_ngrams = _ngrams(answer, 3)
    c_ngrams = _ngrams(context, 3)
    if not a_ngrams:
        ngram_p = 0.0
    else:
        ngram_p = len(a_ngrams & c_ngrams) / len(a_ngrams)

    return round(0.6 * token_p + 0.4 * ngram_p, 4)


__all__ = [
    "faithfulness_check",
    "fallback_faithfulness",
    "probe",
    "HealthLensUnavailableEngine",
]
