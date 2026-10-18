"""RAGAS adapter 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「GraphRAG 幻觉评测：RAGAS faithfulness（2026 最成熟通用框架）」。

覆盖：
- probe() 结构、available 布尔、install_hint
- faithfulness_check 未装 ragas 时抛 HealthLensUnavailableEngine（用 monkeypatch 阻断）
- faithfulness_check 参数校验（类型错误、空字符串）
- faithfulness_check 装了 ragas 时（monkeypatch mock）返回合理分数
- fallback_faithfulness 纯 Python baseline：token/ngram overlap 计算正确性
- fallback_faithfulness 边界（空 answer、空 context、完全匹配、完全不匹配、中文分词）
"""
from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.lib.engine_exceptions import HealthLensUnavailableEngine
from app.lib.ragas_adapter import (
    _ngrams,
    _token_set,
    faithfulness_check,
    fallback_faithfulness,
    probe,
)


# ─────────────────────────── 1. probe() ───────────────────────────


class TestProbe:
    def test_probe_returns_dict(self) -> None:
        r = probe()
        assert isinstance(r, dict)

    def test_probe_has_required_keys(self) -> None:
        r = probe()
        for k in ("engine", "available", "version", "install_hint", "note"):
            assert k in r

    def test_probe_engine_name(self) -> None:
        assert probe()["engine"] == "ragas"

    def test_probe_install_hint(self) -> None:
        assert "evaluation" in probe()["install_hint"]

    def test_probe_version_is_str_or_none(self) -> None:
        r = probe()
        assert r["version"] is None or isinstance(r["version"], str)

    def test_probe_available_is_bool(self) -> None:
        assert isinstance(probe()["available"], bool)

    def test_probe_note_differs_by_availability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 未装场景
        monkeypatch.setattr(
            importlib.util, "find_spec",
            lambda name: None if name == "ragas" else ModuleType("x"),
        )
        r = probe()
        assert "未装" in r["note"] or "fail" in r["note"].lower()

        # 已装场景（用 monkeypatch 让 find_spec 返回非 None，import 用 mock）
        fake_module = ModuleType("ragas")
        fake_module.__version__ = "0.3.0"
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake_module if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake_module)
        r2 = probe()
        assert r2["available"] is True
        assert r2["version"] == "0.3.0"


# ─────────────────────────── 2. faithfulness_check ───────────────────────────


class TestFaithfulnessCheck:
    def test_raises_when_ragas_not_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未装 ragas 时应抛 HealthLensUnavailableEngine（fail-loud）。"""
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        with pytest.raises(HealthLensUnavailableEngine) as exc:
            faithfulness_check("answer", "context")
        assert exc.value.engine_name == "ragas"
        assert exc.value.required_package == "ragas"
        assert "evaluation" in exc.value.pip_command

    def test_answer_must_be_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """答参类型错误 → ValueError。"""
        fake = ModuleType("ragas")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        with pytest.raises(ValueError, match="answer must be str"):
            faithfulness_check(123, "context")  # type: ignore[arg-type]

    def test_context_must_be_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = ModuleType("ragas")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        with pytest.raises(ValueError, match="context must be str"):
            faithfulness_check("answer", 456)  # type: ignore[arg-type]

    def test_empty_answer_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """answer 空 → 0.0，不抛错。"""
        fake = ModuleType("ragas")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        assert faithfulness_check("", "context") == 0.0

    def test_empty_context_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """context 空 → 0.0，不抛错（无依据时无法判断）。"""
        fake = ModuleType("ragas")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        assert faithfulness_check("answer", "") == 0.0

    def test_returns_float_when_ragas_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """mock ragas.Faithfulness 返回 0.7 → faithfulness_check 返回 0.7。"""
        fake = ModuleType("ragas")
        fake_metrics = ModuleType("ragas.metrics")
        mock_metric = MagicMock()
        mock_metric.single_turn_ascore.return_value = 0.7
        fake_metrics.Faithfulness = MagicMock(return_value=mock_metric)
        fake.metrics = fake_metrics
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
        score = faithfulness_check("answer", "context")
        assert score == pytest.approx(0.7)

    def test_dict_result_extract_faithfulness_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ragas 返回 dict 含 'faithfulness' 键 → 提取。"""
        fake = ModuleType("ragas")
        fake_metrics = ModuleType("ragas.metrics")
        mock_metric = MagicMock()
        mock_metric.single_turn_ascore.return_value = {"faithfulness": 0.55}
        fake_metrics.Faithfulness = MagicMock(return_value=mock_metric)
        fake.metrics = fake_metrics
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
        assert faithfulness_check("a", "c") == pytest.approx(0.55)

    def test_dict_result_fallback_to_first_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dict 无 faithfulness/score/value → 取第一个 float。"""
        fake = ModuleType("ragas")
        fake_metrics = ModuleType("ragas.metrics")
        mock_metric = MagicMock()
        mock_metric.single_turn_ascore.return_value = {"note": "x", "value2": 0.42}
        fake_metrics.Faithfulness = MagicMock(return_value=mock_metric)
        fake.metrics = fake_metrics
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
        assert faithfulness_check("a", "c") == pytest.approx(0.42)

    def test_ragas_internal_error_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ragas 内部异常应被包成 HealthLensUnavailableEngine。"""
        fake = ModuleType("ragas")
        fake_metrics = ModuleType("ragas.metrics")
        fake_metrics.Faithfulness = MagicMock(side_effect=RuntimeError("boom"))
        fake.metrics = fake_metrics
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "ragas" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "ragas", fake)
        monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
        with pytest.raises(HealthLensUnavailableEngine):
            faithfulness_check("a", "c")


# ─────────────────────────── 3. fallback_faithfulness ───────────────────────────


class TestFallbackFaithfulness:
    def test_perfect_match_returns_one(self) -> None:
        """answer == context → 分数应接近 1.0。"""
        score = fallback_faithfulness("hello world foo bar", "hello world foo bar")
        assert score == pytest.approx(1.0, abs=0.05)

    def test_no_overlap_returns_zero(self) -> None:
        score = fallback_faithfulness("abc xyz", "pqr stu")
        assert score == pytest.approx(0.0, abs=0.05)

    def test_empty_answer_returns_zero(self) -> None:
        assert fallback_faithfulness("", "some context") == 0.0

    def test_empty_context_returns_zero(self) -> None:
        assert fallback_faithfulness("some answer", "") == 0.0

    def test_whitespace_only_returns_zero(self) -> None:
        assert fallback_faithfulness("   ", "context") == 0.0
        assert fallback_faithfulness("answer", "   ") == 0.0

    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must be str"):
            fallback_faithfulness(123, "context")  # type: ignore[arg-type]

    def test_score_in_range(self) -> None:
        for a, c in [
            ("炎症轴偏高", "炎症轴评分较高，建议关注 hs-CRP 指标"),
            ("血糖正常", "高血压和糖尿病是常见慢性病"),
            ("", ""),
            ("同一段话", "同一段话"),
        ]:
            s = fallback_faithfulness(a, c)
            assert 0.0 <= s <= 1.0, f"score {s} out of [0,1] for ({a!r},{c!r})"

    def test_chinese_ngram_works(self) -> None:
        """中文 token 提取应正常，n-gram 命中。"""
        score = fallback_faithfulness("炎症轴 AMPK mTOR", "炎症轴涉及 AMPK 和 mTOR 通路")
        # 至少有 3 个 token 命中 → token_p > 0
        assert score > 0

    def test_partial_overlap(self) -> None:
        """部分 overlap 应介于 0 和 1 之间。"""
        score = fallback_faithfulness("ABC DEF", "ABC XYZ")
        assert 0.0 < score < 1.0


# ─────────────────────────── 4. 辅助函数（tokenize / n-gram） ───────────────────────────


class TestHelpers:
    def test_token_set_basic(self) -> None:
        assert _token_set("Hello world") == {"hello", "world"}

    def test_token_set_chinese(self) -> None:
        """中文字符序列被识别为一个或多个 token（正则 [\u4e00-\u9fff]+ 会合并连续汉字）。"""
        ts = _token_set("炎症轴")
        # 连续汉字会被合并为一个 token（"炎症轴"），而不是拆成 3 个单字
        assert "炎症轴" in ts
        assert len(ts) == 1

    def test_token_set_chinese_spaces(self) -> None:
        """含空格的分词会正确拆开。"""
        ts = _token_set("炎症 轴 AMPK")
        assert "炎症" in ts
        assert "轴" in ts
        assert "ampk" in ts

    def test_token_set_mixed(self) -> None:
        ts = _token_set("hs-CRP 2.5 正常")
        assert len(ts) >= 3  # 至少 hs、crp、2、5、正、常、常
        assert "hs" in ts or "crp" in ts or "hs-crp" in ts  # 具体形态取决于 tokenizer

    def test_ngrams_basic(self) -> None:
        ng = _ngrams("a b c d", 3)
        assert ng == {("a", "b", "c"), ("b", "c", "d")}

    def test_ngrams_too_short(self) -> None:
        ng = _ngrams("a b", 3)
        assert ng == set()

    def test_ngrams_single_token(self) -> None:
        ng = _ngrams("abc", 3)
        assert ng == set()  # 只有 1 个 token，不够 3-gram
