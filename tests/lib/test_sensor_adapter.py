"""L2 表征层 sensor_adapter 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。
> 可穿戴基础模型（SensorFM / Pulse-PPG / PaPaGei）已经把「传感器 → 健康表征」
> 这层商品化。HealthLens 的对策：**用 adapter 隔离重型科学层与零依赖内核**。

覆盖：
- 未装库时 probe 返回 available=False + 明确 reason
- load_pulse_ppg_model 未装时抛 HealthLensUnavailableEngine
- load_papagei_model 未装时抛 HealthLensUnavailableEngine
- zero_shot_embed_wellness 输出维度正确、确定性
- zero_shot_embed_wellness 边界（空、太短、NaN）
- Mock 一个"装了 torch" 的场景（monkeypatch importlib.util.find_spec）

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import importlib.util
import math
import random
from typing import Any

import pytest

from app.lib.sensor_adapter import (
    FEATURE_DIM,
    HealthLensUnavailableEngine,
    SensorModelProbe,
    _band_powers,
    _autocorr,
    _spectral_features,
    _window_features,
    list_available_engines,
    load_papagei_model,
    load_pulse_ppg_model,
    zero_shot_embed_wellness,
)


# ─────────────────────────── fixtures ───────────────────────────

def _sine(n: int, freq: float = 2.0, sr: float = 100.0, amp: float = 1.0) -> list[float]:
    return [amp * math.sin(2 * math.pi * freq * i / sr) for i in range(n)]


def _noise(n: int, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0, 1) for _ in range(n)]


@pytest.fixture
def sine_signal() -> list[float]:
    return _sine(500, freq=2.0, sr=100.0)


@pytest.fixture
def noise_signal() -> list[float]:
    return _noise(1000, seed=2)


# ─────────────────────────── 1. Probe ───────────────────────────

class TestProbe:
    def test_returns_list_of_probes(self) -> None:
        probes = list_available_engines()
        assert isinstance(probes, list)
        assert len(probes) == 3

    def test_probes_all_have_engine_name(self) -> None:
        probes = list_available_engines()
        for p in probes:
            assert isinstance(p, SensorModelProbe)
            assert p.engine_name
            assert isinstance(p.available, bool)
            assert isinstance(p.reason, str)
            assert len(p.reason) > 0

    def test_torch_probe_not_installed(self) -> None:
        # CI 无 torch，明确返回 available=False
        probes = list_available_engines()
        torch_probe = probes[0]
        assert torch_probe.engine_name == "Pulse-PPG (torch)"
        # 若 torch 未装：available=False + reason 提到 not installed
        if not importlib.util.find_spec("torch"):
            assert torch_probe.available is False
            assert "not installed" in torch_probe.reason
            assert torch_probe.version is None

    def test_transformers_probe(self) -> None:
        probes = list_available_engines()
        tf_probe = probes[1]
        assert tf_probe.engine_name == "transformers"
        if not importlib.util.find_spec("transformers"):
            assert tf_probe.available is False
            assert "not installed" in tf_probe.reason

    def test_sentence_transformers_probe(self) -> None:
        probes = list_available_engines()
        st_probe = probes[2]
        assert st_probe.engine_name == "sentence-transformers"
        if not importlib.util.find_spec("sentence_transformers"):
            assert st_probe.available is False
            assert "not installed" in st_probe.reason

    def test_probe_to_dict(self) -> None:
        probes = list_available_engines()
        d = probes[0].to_dict()
        assert set(d.keys()) == {"engine_name", "available", "reason", "version"}


# ─────────────────────────── 2. Load Pulse-PPG ───────────────────────────

class TestLoadPulsePPG:
    def test_raises_when_torch_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 强制 torch 探测失败
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "torch" else importlib.util.find_spec(name))
        with pytest.raises(HealthLensUnavailableEngine, match="torch"):
            load_pulse_ppg_model()

    def test_raises_on_weight_load_without_checkpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 模拟 torch 已装
        _make_fake_torch(monkeypatch, version="2.3.0")
        with pytest.raises(HealthLensUnavailableEngine, match="checkpoint"):
            load_pulse_ppg_model(load_weights=True)

    def test_dry_run_returns_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_fake_torch(monkeypatch, version="2.3.0")
        result = load_pulse_ppg_model(load_weights=False)
        assert result["engine_name"] == "Pulse-PPG"
        assert result["loaded"] is True
        assert result["dry_run"] is True
        assert "torch_version" in result


# ─────────────────────────── 3. Load PaPaGei ───────────────────────────

class TestLoadPaPaGei:
    def test_raises_when_torch_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "torch" else importlib.util.find_spec(name))
        with pytest.raises(HealthLensUnavailableEngine, match="torch"):
            load_papagei_model()

    def test_raises_on_weight_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_fake_torch(monkeypatch, version="2.3.0")
        with pytest.raises(HealthLensUnavailableEngine, match="checkpoint"):
            load_papagei_model(load_weights=True)

    def test_dry_run_returns_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_fake_torch(monkeypatch, version="2.3.0")
        result = load_papagei_model(load_weights=False)
        assert result["engine_name"] == "PaPaGei"
        assert result["loaded"] is True
        assert result["dry_run"] is True


def _make_fake_torch(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    """Mock importlib.util.find_spec 让 torch 探测成功，并注入假 torch 模块。"""
    # find_spec 返回非 None
    def fake_find_spec(name: str):
        if name == "torch":
            class _Spec:
                pass
            return _Spec()
        return importlib.util.find_spec(name)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    # 注入假 torch 模块
    class _FakeTorch:
        __version__ = version

    monkeypatch.setitem(__import__("sys").modules, "torch", _FakeTorch)


# ─────────────────────────── 4. zero_shot_embed_wellness ───────────────────────────

class TestZeroShotEmbed:
    def test_feature_dim_constant(self) -> None:
        assert FEATURE_DIM == 20

    def test_output_dim_is_20(self, sine_signal: list[float]) -> None:
        embeds = zero_shot_embed_wellness(sine_signal, sample_rate_hz=100, window_size=128)
        assert len(embeds) > 0
        for e in embeds:
            assert len(e) == FEATURE_DIM, f"期望 {FEATURE_DIM} 维，实际 {len(e)}"

    def test_deterministic(self, sine_signal: list[float]) -> None:
        e1 = zero_shot_embed_wellness(sine_signal, 100, 128, 64)
        e2 = zero_shot_embed_wellness(sine_signal, 100, 128, 64)
        assert e1 == e2

    def test_strict_stride_windows_count(self, sine_signal: list[float]) -> None:
        # window=128, stride=128, n=500 → (500-128)/128 = 2.9 → 3 windows (0, 128, 256, 384 → 最后一窗起始 384, 500-128=372 < 384, 所以最后能起的是 372-64=...)
        # 实际算法：range(0, n-window+1, stride) = range(0, 373, 128) = [0, 128, 256, 384]
        # 但 384+128=512 > 500 → 超出 range
        # range(0, 373, 128) 生成 0, 128, 256, 384 —— 但 384+128=512 > 500，切片 [384:512] 只到 500，长度 116 < 128
        # 我们的实现在切片后 window 长度可能不足 128
        # 修正：算法是 range(0, len-window+1, stride)
        n = len(sine_signal)
        expected = len(range(0, n - 128 + 1, 128))
        embeds = zero_shot_embed_wellness(sine_signal, 100, 128, 128)
        assert len(embeds) == expected

    def test_overlapping_windows(self, sine_signal: list[float]) -> None:
        e = zero_shot_embed_wellness(sine_signal, 100, 128, 64)
        # 重叠模式产生更多窗口
        n = len(sine_signal)
        expected = len(range(0, n - 128 + 1, 64))
        assert len(e) == expected
        # 且多于非重叠
        non_overlapping = zero_shot_embed_wellness(sine_signal, 100, 128, 128)
        assert len(e) > len(non_overlapping)

    def test_empty_signal_raises(self) -> None:
        with pytest.raises(ValueError, match="空"):
            zero_shot_embed_wellness([], 100, 128)

    def test_short_signal_raises(self) -> None:
        with pytest.raises(ValueError, match="window_size"):
            zero_shot_embed_wellness([1.0, 2.0, 3.0], 100, 128)

    def test_non_list_signal_raises(self) -> None:
        with pytest.raises(TypeError):
            zero_shot_embed_wellness("not a list", 100, 128)  # type: ignore[arg-type]

    def test_invalid_sample_rate_raises(self, sine_signal: list[float]) -> None:
        with pytest.raises(ValueError, match="sample_rate_hz"):
            zero_shot_embed_wellness(sine_signal, 0, 128)

    def test_nan_filled(self) -> None:
        # NaN 会被前向填充，不静默删除
        sig = [1.0, 2.0, float("nan"), 4.0, 5.0, 6.0, 7.0, 8.0] + [float(i) for i in range(120)]
        e = zero_shot_embed_wellness(sig, 100, 128)
        # 不抛错，且第一个窗口的 mean 应接近正常值
        assert len(e) > 0
        # 第一个窗口的 mean 应存在
        assert isinstance(e[0][0], (int, float))

    def test_numpy_compat(self) -> None:
        # numpy array 输入兼容
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy not available")
        arr = np.array([float(i) for i in range(200)])
        e = zero_shot_embed_wellness(arr, 100, 128)
        assert len(e) > 0
        assert len(e[0]) == FEATURE_DIM


# ─────────────────────────── 5. _window_features ───────────────────────────

class TestWindowFeatures:
    def test_returns_20_features(self) -> None:
        window = _sine(128, freq=2.0, sr=100.0)
        feats = _window_features(window, 100)
        assert len(feats) == FEATURE_DIM

    def test_sine_dominant_freq(self) -> None:
        # 2 Hz 正弦 → dominant_freq[12] 接近 2
        window = _sine(256, freq=2.0, sr=100.0)
        feats = _window_features(window, 100)
        assert feats[12] == pytest.approx(2.0, abs=0.5)

    def test_constant_window_features(self) -> None:
        window = [5.0] * 128
        feats = _window_features(window, 100)
        # mean=5, std=0, min=max=5
        assert feats[0] == 5.0
        assert feats[1] == 0.0
        assert feats[4] == 5.0
        assert feats[5] == 5.0
        assert feats[6] == 0.0  # cv=0

    def test_band_powers_sum_to_one(self) -> None:
        rng = random.Random(3)
        window = [rng.gauss(0, 1) for _ in range(256)]
        feats = _window_features(window, 100)
        bp_sum = feats[9] + feats[10] + feats[11]
        assert bp_sum == pytest.approx(1.0, abs=1e-6)


# ─────────────────────────── 6. Helpers ───────────────────────────

class TestHelpers:
    def test_band_powers_sum(self) -> None:
        rng = random.Random(4)
        sig = [rng.gauss(0, 1) for _ in range(500)]
        bp = _band_powers(sig, 100)
        assert sum(bp) == pytest.approx(1.0, abs=1e-6)

    def test_autocorr_lag1_near_one_for_trend(self) -> None:
        sig = [float(i) for i in range(100)]
        ac1 = _autocorr(sig, 1)
        assert ac1 > 0.9

    def test_autocorr_lag1_near_zero_for_noise(self) -> None:
        rng = random.Random(5)
        sig = [rng.gauss(0, 1) for _ in range(500)]
        ac1 = _autocorr(sig, 1)
        assert abs(ac1) < 0.1

    def test_autocorr_short_series_zero(self) -> None:
        assert _autocorr([1.0, 2.0], 1) == 0.0

    def test_spectral_features_in_range(self) -> None:
        rng = random.Random(6)
        sig = [rng.gauss(0, 1) for _ in range(500)]
        dom, ent = _spectral_features(sig, 100)
        assert 0.0 <= ent <= 1.0 + 1e-9
        assert dom >= 0.0


# ─────────────────────────── 7. HealthLensUnavailableEngine ───────────────────────────

class TestException:
    def test_is_runtime_error(self) -> None:
        assert issubclass(HealthLensUnavailableEngine, RuntimeError)

    def test_message_preserved(self) -> None:
        try:
            raise HealthLensUnavailableEngine("test reason")
        except HealthLensUnavailableEngine as e:
            assert "test reason" in str(e)
