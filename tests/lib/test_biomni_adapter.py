"""Biomni adapter 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「外部证据工具：Biomni（Apache-2.0，Science 2026-07，★3.9k，极活跃）」。

覆盖：
- probe() 结构、available 布尔、install_hint（含"可能未公开发布"提示）
- query_biomedical_claim 未装 biomni 时抛 HealthLensUnavailableEngine（用 monkeypatch 阻断）
- query_biomedical_claim 参数校验（类型错误、空 claim）
- query_biomedical_claim 装了 biomni 时（monkeypatch mock）：
  - biomni.query 入口 → 返回结构化结果
  - biomni.search 入口 → 返回结构化结果
  - biomni.Client 入口 → 返回结构化结果
  - 未知 API 形态 → 返回 found=False + note
  - 内部异常被包成 HealthLensUnavailableEngine
- 返回结构完整性（claim/found/score/sources/engine/note）
- sources 归一化（dict/list 两种形态、id/title/snippet/score 字段）
"""
from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from app.lib.biomni_adapter import probe, query_biomedical_claim
from app.lib.engine_exceptions import HealthLensUnavailableEngine


# ─────────────────────────── 1. probe() ───────────────────────────


class TestProbe:
    def test_probe_returns_dict(self) -> None:
        assert isinstance(probe(), dict)

    def test_probe_has_required_keys(self) -> None:
        r = probe()
        for k in ("engine", "available", "version", "install_hint", "note"):
            assert k in r

    def test_probe_engine_name(self) -> None:
        assert probe()["engine"] == "biomni"

    def test_probe_install_hint_mentions_availability(self) -> None:
        """install_hint 应明确告知 biomni 可能未公开发布。"""
        hint = probe()["install_hint"]
        assert "biomni" in hint.lower() or "pip install" in hint.lower()

    def test_probe_available_is_bool(self) -> None:
        assert isinstance(probe()["available"], bool)

    def test_probe_unavailable_note_mentions_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        r = probe()
        assert r["available"] is False
        assert r["version"] is None
        assert "未装" in r["note"] or "biomni" in r["note"].lower()

    def test_probe_available_when_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = ModuleType("biomni")
        fake.__version__ = "1.0.0"
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "biomni" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "biomni", fake)
        r = probe()
        assert r["available"] is True
        assert r["version"] == "1.0.0"


# ─────────────────────────── 2. query_biomedical_claim 基础校验 ───────────────────────────


class TestQueryParamValidation:
    def test_raises_when_biomni_not_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未装 biomni 时抛 HealthLensUnavailableEngine（fail-loud）。"""
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        with pytest.raises(HealthLensUnavailableEngine) as exc:
            query_biomedical_claim("some claim")
        assert exc.value.engine_name == "biomni"

    def test_claim_must_be_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = ModuleType("biomni")
        fake.__version__ = "1.0"
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "biomni" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "biomni", fake)
        with pytest.raises(ValueError, match="claim must be str"):
            query_biomedical_claim(123)  # type: ignore[arg-type]

    def test_claim_must_be_non_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = ModuleType("biomni")
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "biomni" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "biomni", fake)
        with pytest.raises(ValueError, match="non-empty"):
            query_biomedical_claim("")


# ─────────────────────────── 3. query_biomedical_claim mock 场景 ───────────────────────────


class TestQueryWithMockedBiomni:
    def _install_mock(self, monkeypatch: pytest.MonkeyPatch, **biomni_attrs) -> ModuleType:
        """安装 mock biomni 模块到 sys.modules 与 importlib.util.find_spec。"""
        fake = ModuleType("biomni")
        fake.__version__ = "1.0.0"
        for k, v in biomni_attrs.items():
            setattr(fake, k, v)
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "biomni" else ModuleType("x"))
        monkeypatch.setitem(sys.modules, "biomni", fake)
        return fake

    def test_query_entry_dict_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """biomni.query 入口 + dict 返回 → 正确解析 sources。"""
        def mock_query(claim, **kwargs):
            return {
                "results": [
                    {"id": "DOI-1", "title": "Title 1", "snippet": "Snippet 1", "score": 0.9},
                    {"id": "DOI-2", "title": "Title 2", "snippet": "Snippet 2", "score": 0.7},
                ]
            }

        self._install_mock(monkeypatch, query=mock_query)
        r = query_biomedical_claim("AMPK activates autophagy")
        assert r["engine"] == "biomni"
        assert r["claim"] == "AMPK activates autophagy"
        assert r["found"] is True
        assert r["score"] == pytest.approx(0.9)  # 最高分
        assert len(r["sources"]) == 2
        assert r["sources"][0]["id"] == "DOI-1"
        assert "queried" in r["note"]

    def test_query_entry_list_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """biomni.query 返回 list → 也能解析。"""
        def mock_query(claim, **kwargs):
            return [{"id": "X", "title": "T", "snippet": "S", "score": 0.5}]

        self._install_mock(monkeypatch, query=mock_query)
        r = query_biomedical_claim("c")
        assert r["found"] is True
        assert len(r["sources"]) == 1
        assert r["score"] == pytest.approx(0.5)

    def test_search_entry_when_query_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 query 但有 search → 用 search。"""
        def mock_search(claim, **kwargs):
            return [{"id": "S1", "title": "T", "snippet": "S", "score": 0.3}]

        self._install_mock(monkeypatch, search=mock_search)
        r = query_biomedical_claim("c")
        assert r["found"] is True
        assert r["score"] == pytest.approx(0.3)

    def test_client_entry_when_query_and_search_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 query/search 但有 Client → 用 Client().query。"""
        class FakeClient:
            def __init__(self):
                self.call_log = []

            def query(self, claim, **kwargs):
                self.call_log.append(claim)
                return [{"id": "C1", "title": "T", "text": "Body", "score": 0.4}]

        self._install_mock(monkeypatch, Client=FakeClient)
        r = query_biomedical_claim("claim-x")
        assert r["found"] is True
        assert r["sources"][0]["id"] == "C1"
        assert r["sources"][0]["snippet"] == "Body"  # 从 text 字段回填
        assert r["score"] == pytest.approx(0.4)

    def test_unknown_api_returns_found_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """biomni 无任何已知 API → 返回 found=False + note 说明。"""
        self._install_mock(monkeypatch)  # 空模块
        r = query_biomedical_claim("claim")
        assert r["found"] is False
        assert r["score"] == 0.0
        assert r["sources"] == []
        assert "no known API" in r["note"]

    def test_sources_missing_score_defaults_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """source item 无 score 字段 → 默认 0.0。"""
        def mock_query(claim, **kwargs):
            return [{"id": "X", "title": "T", "snippet": "S"}]

        self._install_mock(monkeypatch, query=mock_query)
        r = query_biomedical_claim("c")
        assert r["found"] is True
        assert r["sources"][0]["score"] == 0.0

    def test_non_dict_items_in_list_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list 中混入非 dict 项应被过滤。"""
        def mock_query(claim, **kwargs):
            return ["not-dict", None, {"id": "X", "title": "T", "snippet": "S", "score": 0.6}]

        self._install_mock(monkeypatch, query=mock_query)
        r = query_biomedical_claim("c")
        assert len(r["sources"]) == 1
        assert r["sources"][0]["id"] == "X"

    def test_biomni_internal_error_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """biomni.query 抛异常 → 被包成 HealthLensUnavailableEngine。"""
        def mock_query(claim, **kwargs):
            raise RuntimeError("network error")

        self._install_mock(monkeypatch, query=mock_query)
        with pytest.raises(HealthLensUnavailableEngine) as exc:
            query_biomedical_claim("c")
        assert exc.value.engine_name == "biomni"
        assert exc.value.required_package == "biomni"
        # 底层异常消息应被包进 str(exc)
        assert "network error" in str(exc.value)

    def test_empty_results_found_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """query 返回空结果 → found=False。"""
        def mock_query(claim, **kwargs):
            return {"results": []}

        self._install_mock(monkeypatch, query=mock_query)
        r = query_biomedical_claim("c")
        assert r["found"] is False
        assert r["score"] == 0.0

    def test_kwargs_forwarded_to_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """kwargs 应透传给 biomni.query。"""
        captured = {}

        def mock_query(claim, **kwargs):
            captured.update(kwargs)
            return []

        self._install_mock(monkeypatch, query=mock_query)
        query_biomedical_claim("c", top_k=5, limit=10)
        assert captured.get("top_k") == 5
        assert captured.get("limit") == 10
