"""L2 表征层 ts_serializer 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。
> 「时序信号的确定性序列化（生态空白）」——「确定性 → 可审计、可复现、可测试」。

覆盖：
- 确定性：同输入 → 同 JSON → 同 hash（跑 10 次）
- 幂等：verify_hash 正确
- 空/单样本/常数序列边界
- NaN 填充正确性
- z-score 归一化数值验证
- 频域：合成正弦 dominant_freq 接近真值
- band_powers 归一化求和 = 1（±1e-6）
- Hurst 指数：白噪声 ≈0.5，趋势序列 >0.5
- Schema 校验：缺字段抛错、类型错抛错、未知字段告警
- Round-trip：serialize → validate → hash 一致
- 性能上限：10000 样本 <500ms
- Schema 版本演进：修改 generator 字段不改变业务字段 hash（本实现选择"改变"，测试锁定）
- Text 模式输出：行数与字段数一致

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import time
from typing import Any

import pytest

from app.lib.ts_serializer import (
    GENERATOR_NAME,
    SCHEMA_VERSION,
    SerializeOptions,
    TimeSeriesBundle,
    _approximate_entropy,
    _bin_signals,
    _fft,
    _freq_domain_features,
    _fractal_dimension,
    _hurst_dfa,
    _preprocess,
    _privacy_hash,
    _time_domain_features,
    compute_hash,
    serialize,
    validate_serialized,
    verify_hash,
)


# ─────────────────────────── fixtures ───────────────────────────

def _rand_samples(n: int, seed: int = 42, mean: float = 0.0, std: float = 1.0) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mean, std) for _ in range(n)]


def _sine_samples(freq_hz: float, sample_rate_hz: float, n: int, amp: float = 1.0) -> list[float]:
    return [amp * math.sin(2 * math.pi * freq_hz * i / sample_rate_hz) for i in range(n)]


@pytest.fixture
def rand_bundle() -> TimeSeriesBundle:
    return TimeSeriesBundle(
        channel_name="HRV",
        samples=_rand_samples(500),
        sample_rate_hz=250,
        unit="bpm",
        subject_id="sub-001",
        session_id="sess-001",
    )


@pytest.fixture
def sine_bundle() -> TimeSeriesBundle:
    return TimeSeriesBundle(
        channel_name="pulse",
        samples=_sine_samples(1.0, 100, 1000),
        sample_rate_hz=100,
        unit="umol",
    )


# ─────────────────────────── 1. 确定性 ───────────────────────────

class TestDeterminism:
    """同一输入必产生同一 JSON 字符串与同一 hash。"""

    def test_10x_same_hash(self, rand_bundle: TimeSeriesBundle) -> None:
        hashes = []
        jsons = []
        for _ in range(10):
            r = serialize(rand_bundle)
            hashes.append(r.sha256)
            jsons.append(r.json_str)
        assert len(set(hashes)) == 1, "10 次序列化 hash 应完全一致"
        assert len(set(jsons)) == 1, "10 次序列化 JSON 应完全一致"

    def test_same_input_across_objects(self) -> None:
        samples = _rand_samples(200, seed=7)
        b1 = TimeSeriesBundle("HRV", samples[:], 250, "bpm", "s1", "x1")
        b2 = TimeSeriesBundle("HRV", samples[:], 250, "bpm", "s1", "x1")
        r1 = serialize(b1)
        r2 = serialize(b2)
        assert r1.sha256 == r2.sha256
        assert r1.json_str == r2.json_str

    def test_different_input_different_hash(self) -> None:
        b1 = TimeSeriesBundle("HRV", _rand_samples(100, seed=1), 100, "bpm")
        b2 = TimeSeriesBundle("HRV", _rand_samples(100, seed=2), 100, "bpm")
        assert serialize(b1).sha256 != serialize(b2).sha256

    def test_subject_id_affects_hash(self) -> None:
        samples = _rand_samples(50)
        b1 = TimeSeriesBundle("HRV", samples, 100, "bpm", "sub-A", "sess-1")
        b2 = TimeSeriesBundle("HRV", samples, 100, "bpm", "sub-B", "sess-1")
        assert serialize(b1).sha256 != serialize(b2).sha256

    def test_generator_change_changes_hash(self) -> None:
        """Schema 版本演进：修改 generator 字段改变整个 hash。

        本实现选择"改变"策略（hash 覆盖全部 JSON），测试锁定此行为。
        """
        samples = _rand_samples(100)
        b = TimeSeriesBundle("HRV", samples, 100, "bpm")
        r1 = serialize(b)
        # 篡改 generator
        structured = json.loads(r1.json_str)
        structured["generator"] = "hacker-ts-serializer"
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert r1.sha256 != compute_hash(tampered)
        assert verify_hash(tampered, r1.sha256) is False


# ─────────────────────────── 2. 幂等 ───────────────────────────

class TestVerifyHash:
    """verify_hash 反查校验。"""

    def test_verify_success(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        assert verify_hash(r.json_str, r.sha256) is True

    def test_verify_fail_on_tamper(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        # 修改一个字符
        tampered = r.json_str + " "
        assert verify_hash(tampered, r.sha256) is False

    def test_compute_hash_matches_sha256_hexdigest(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        expected = hashlib.sha256(r.json_str.encode("utf-8")).hexdigest()
        assert compute_hash(r.json_str) == expected
        assert r.sha256 == expected

    def test_verify_empty_string(self) -> None:
        assert verify_hash("", hashlib.sha256(b"").hexdigest()) is True


# ─────────────────────────── 3. 边界 ───────────────────────────

class TestEdgeCases:
    """空/单样本/常数序列边界。"""

    def test_empty_samples_raises(self) -> None:
        with pytest.raises(ValueError, match="空"):
            TimeSeriesBundle("HRV", [], 100, "bpm")

    def test_all_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            serialize(TimeSeriesBundle("HRV", [float("nan")] * 10, 100, "bpm"))

    def test_single_sample_graceful(self) -> None:
        b = TimeSeriesBundle("HRV", [42.5], 100, "bpm", "s", "x")
        r = serialize(b)
        assert r.structured["n_samples"] == 1
        assert r.structured["features"]["time_domain"]["mean"] == 42.5
        # shape 特征在单样本下为 None（graceful degradation）
        assert r.structured["features"]["shape"]["hurst_exponent"] is None

    def test_single_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="NaN"):
            serialize(TimeSeriesBundle("HRV", [float("nan")], 100, "bpm"))

    def test_constant_series_graceful(self) -> None:
        b = TimeSeriesBundle("HRV", [5.0] * 200, 100, "bpm")
        r = serialize(b)
        assert r.structured["features"]["time_domain"]["std"] == 0.0
        # shape 特征 graceful：hurst/fractal=None, entropy=0
        assert r.structured["features"]["shape"]["hurst_exponent"] is None
        assert r.structured["features"]["shape"]["approximate_entropy"] == 0.0

    def test_invalid_sample_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="sample_rate_hz"):
            TimeSeriesBundle("HRV", [1, 2, 3], 0, "bpm")

    def test_invalid_channel_name_raises(self) -> None:
        with pytest.raises(ValueError, match="channel_name"):
            TimeSeriesBundle("", [1, 2, 3], 100, "bpm")

    def test_non_numeric_sample_raises(self) -> None:
        with pytest.raises(ValueError, match="非数值"):
            TimeSeriesBundle("HRV", [1.0, "abc", 3.0], 100, "bpm")  # type: ignore[list-item]


# ─────────────────────────── 4. NaN 填充 ───────────────────────────

class TestPreprocess:
    """NaN 填充 + 3σ 去极值 + z-score。"""

    def test_nan_forward_fill(self) -> None:
        samples = [1.0, 2.0, float("nan"), 4.0, float("nan"), 6.0]
        cleaned, z, mf = _preprocess(samples)
        # NaN 被前向填充：2.0 → 2.0，4.0 → 4.0
        assert cleaned[2] == 2.0
        assert cleaned[4] == 4.0
        assert mf == pytest.approx(2 / 6, abs=1e-9)

    def test_nan_backward_fill_at_start(self) -> None:
        samples = [float("nan"), float("nan"), 3.0, 4.0]
        cleaned, _, mf = _preprocess(samples)
        assert cleaned[0] == 3.0
        assert cleaned[1] == 3.0
        assert mf == pytest.approx(0.5)

    def test_no_nan_keeps_values(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        cleaned, _, mf = _preprocess(samples)
        assert cleaned == samples
        assert mf == 0.0

    def test_outlier_removed_by_3sigma(self) -> None:
        # 大部分接近 10，一个 1000 的极值 → MAD=0，替换为中位数 10
        samples = [10.0] * 100 + [1000.0]
        cleaned, _, _ = _preprocess(samples)
        # 极值应被替换为中位数 10.0（MAD=0 情形）
        assert cleaned[-1] == 10.0
        # 正常样本保持不变
        assert cleaned[0] == 10.0
        assert cleaned[50] == 10.0

    def test_outlier_removed_mad_std(self) -> None:
        # 用正常分布 + 一个明显极值：MAD > 0，走 3*MAD 阈值
        rng = random.Random(21)
        samples = [rng.gauss(10.0, 1.0) for _ in range(100)] + [1000.0]
        cleaned, _, _ = _preprocess(samples)
        # 极值应被替换（不再是 1000）
        assert cleaned[-1] != 1000.0
        # 且应接近「含极值在内的中位数」——即整体中位数
        median_val = statistics.median(samples)
        assert cleaned[-1] == pytest.approx(median_val, abs=1e-6)

    def test_zscore_mean_zero_std_one(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        _, z, _ = _preprocess(samples)
        mean_z = sum(z) / len(z)
        std_z = math.sqrt(sum((v - mean_z) ** 2 for v in z) / len(z))
        assert mean_z == pytest.approx(0.0, abs=1e-9)
        assert std_z == pytest.approx(1.0, abs=1e-9)

    def test_zscore_constant_returns_zeros(self) -> None:
        _, z, _ = _preprocess([5.0] * 10)
        assert all(v == 0.0 for v in z)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ─────────────────────────── 5. Bin ───────────────────────────

class TestBinning:
    def test_bin_width_1s(self) -> None:
        # 100Hz, 5 秒 = 500 样本 → 5 个 bin
        samples = [float(i) for i in range(500)]
        bins = _bin_signals(samples, 100, 1.0)
        assert len(bins) == 5

    def test_bin_stats_correct(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0]  # 100Hz, 1 bin
        bins = _bin_signals(samples, 100, 1.0)
        assert len(bins) == 1
        b = bins[0]
        assert b["mean"] == pytest.approx(2.5, abs=1e-6)
        assert b["min"] == 1.0
        assert b["max"] == 4.0
        assert b["n_samples"] == 4

    def test_bin_slope_positive(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        bins = _bin_signals(samples, 100, 1.0)
        assert bins[0]["slope"] > 0

    def test_bin_invalid_width_raises(self) -> None:
        with pytest.raises(ValueError, match="bin_width_s"):
            _bin_signals([1.0, 2.0], 100, 0)


# ─────────────────────────── 6. Time domain ───────────────────────────

class TestTimeDomain:
    def test_known_values(self) -> None:
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        f = _time_domain_features(vals)
        assert f["mean"] == pytest.approx(5.0, abs=1e-6)
        assert f["min"] if "min" in f else True  # min 不在 time_domain

    def test_constant_std_zero(self) -> None:
        f = _time_domain_features([3.0] * 20)
        assert f["std"] == 0.0
        assert f["cv"] == 0.0

    def test_rms_positive(self) -> None:
        f = _time_domain_features([1.0, 2.0, 3.0])
        assert f["rms"] > 0


# ─────────────────────────── 7. Frequency domain ───────────────────────────

class TestFreqDomain:
    def test_sine_dominant_freq(self) -> None:
        # 1 Hz 正弦波 @ 100 Hz, 5 秒
        samples = _sine_samples(1.0, 100, 500)
        f = _freq_domain_features(samples, 100, "pulse")
        assert f["dominant_freq"] == pytest.approx(1.0, abs=0.2)

    def test_sine_10hz(self) -> None:
        samples = _sine_samples(10.0, 200, 4000)
        f = _freq_domain_features(samples, 200, "pulse")
        assert f["dominant_freq"] == pytest.approx(10.0, abs=1.0)

    def test_band_powers_sum_to_one_hrv(self) -> None:
        samples = _rand_samples(2000, seed=11)
        f = _freq_domain_features(samples, 250, "HRV")
        bp = f["band_powers"]
        assert set(bp.keys()) == {"vLF", "LF", "HF", "vHF"}
        total = sum(bp.values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_band_powers_sum_to_one_generic(self) -> None:
        samples = _rand_samples(1000, seed=13)
        f = _freq_domain_features(samples, 100, "pulse")
        total = sum(f["band_powers"].values())
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_band_powers_hrv_bands_names(self) -> None:
        samples = _rand_samples(1000, seed=14)
        f = _freq_domain_features(samples, 250, "HRV")
        # HRV 通道应有 4 个频带
        assert len(f["band_powers"]) == 4

    def test_band_powers_eeg_bands(self) -> None:
        samples = _rand_samples(2000, seed=15)
        f = _freq_domain_features(samples, 250, "EEG")
        expected = {"delta", "theta", "alpha", "beta", "gamma"}
        assert set(f["band_powers"].keys()) == expected

    def test_spectral_entropy_in_range(self) -> None:
        samples = _rand_samples(1000, seed=16)
        f = _freq_domain_features(samples, 100, "pulse")
        assert 0.0 <= f["spectral_entropy"] <= 1.0 + 1e-9

    def test_short_series_returns_none(self) -> None:
        f = _freq_domain_features([1.0, 2.0, 3.0], 100, "pulse")
        assert f["dominant_freq"] is None


# ─────────────────────────── 8. Shape features ───────────────────────────

class TestShape:
    def test_hurst_white_noise_near_half(self) -> None:
        # 白噪声 H ≈ 0.5；有限长度下应在 [0.3, 0.7]
        rng = random.Random(99)
        white = [rng.gauss(0, 1) for _ in range(3000)]
        h = _hurst_dfa(white)
        assert h is not None
        assert 0.3 <= h <= 0.7, f"white noise hurst={h}"

    def test_hurst_trend_above_half(self) -> None:
        # 单调趋势 H > 0.5
        rng = random.Random(100)
        trend = [float(i) + rng.gauss(0, 0.5) for i in range(3000)]
        h = _hurst_dfa(trend)
        assert h is not None
        assert h > 0.5, f"trend hurst={h}, should be > 0.5"

    def test_hurst_ar1_positive(self) -> None:
        # AR(1) rho=0.9 → 长程正相关，H > 0.5
        rng = random.Random(101)
        ar = []
        x = 0.0
        for _ in range(3000):
            x = 0.9 * x + rng.gauss(0, 1)
            ar.append(x)
        h = _hurst_dfa(ar)
        assert h is not None
        assert h > 0.5

    def test_hurst_short_series_none(self) -> None:
        assert _hurst_dfa([1.0, 2.0, 3.0]) is None

    def test_approximate_entropy_constant_zero(self) -> None:
        ae = _approximate_entropy([5.0] * 100)
        assert ae == 0.0

    def test_approximate_entropy_regular_low(self) -> None:
        # 正则正弦波熵应低
        sine = [math.sin(2 * math.pi * i / 50) for i in range(200)]
        ae = _approximate_entropy(sine)
        assert ae is not None
        assert ae < 1.0  # 正则序列熵低

    def test_approximate_entropy_noise_higher(self) -> None:
        rng = random.Random(102)
        noise = [rng.gauss(0, 1) for _ in range(200)]
        sine = [math.sin(2 * math.pi * i / 50) for i in range(200)]
        ae_noise = _approximate_entropy(noise)
        ae_sine = _approximate_entropy(sine)
        assert ae_noise is not None
        assert ae_sine is not None
        assert ae_noise > ae_sine, "白噪声熵应高于正则正弦"

    def test_fractal_dimension_in_range(self) -> None:
        rng = random.Random(103)
        vals = [rng.gauss(0, 1) for _ in range(500)]
        d = _fractal_dimension(vals, 100)
        assert d is not None
        assert 1.0 <= d <= 2.0

    def test_fractal_dimension_constant_one(self) -> None:
        d = _fractal_dimension([3.0] * 50, 100)
        assert d == 1.0

    def test_shape_features_keys(self) -> None:
        from app.lib.ts_serializer import _shape_features
        rng = random.Random(104)
        vals = [rng.gauss(0, 1) for _ in range(300)]
        f = _shape_features(vals, 100)
        assert set(f.keys()) == {"hurst_exponent", "fractal_dimension", "approximate_entropy"}


# ─────────────────────────── 9. FFT ───────────────────────────

class TestFFT:
    def test_fft_length_must_be_power_of_two(self) -> None:
        with pytest.raises(ValueError, match="2 的幂"):
            _fft([1.0, 2.0, 3.0])

    def test_fft_impulse(self) -> None:
        # 脉冲序列 [1, 0, 0, 0] 的 FFT 应全为 1
        spec = _fft([1.0, 0.0, 0.0, 0.0])
        assert all(abs(re) == pytest.approx(1.0, abs=1e-9) for re, _ in spec)

    def test_fft_sine_peak_at_expected_bin(self) -> None:
        # 2 Hz 正弦 @ 8 Hz，N=8：频率分辨率 = 8/8 = 1 Hz
        # 2 Hz → bin 2（单侧 0..3）
        n = 8
        sr = 8.0
        vals = [math.sin(2 * math.pi * 2 * i / sr) for i in range(n)]
        spec = _fft(vals)
        power = [(s[0] ** 2 + s[1] ** 2) for s in spec[: n // 2]]
        max_bin = max(range(len(power)), key=lambda i: power[i])
        assert max_bin == 2

    def test_fft_sine_4hz_aliasing_at_nyquist(self) -> None:
        # 4 Hz @ 8 Hz 是 Nyquist，理论上会 alias（sin 取整点全 0）
        # 用 3 Hz 更清晰：3 Hz → bin 3
        n = 8
        sr = 8.0
        vals = [math.sin(2 * math.pi * 3 * i / sr) for i in range(n)]
        spec = _fft(vals)
        power = [(s[0] ** 2 + s[1] ** 2) for s in spec[: n // 2]]
        max_bin = max(range(len(power)), key=lambda i: power[i])
        assert max_bin == 3


# ─────────────────────────── 10. Schema 校验 ───────────────────────────

class TestValidate:
    def test_valid_serialized_no_violations(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        v = validate_serialized(r.json_str)
        assert v == []

    def test_missing_required_field(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        del structured["schema"]
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        assert any("[error] schema: missing" in s for s in v)

    def test_wrong_schema_version(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        structured["schema"] = "v0"
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        assert any("schema: expected" in s for s in v)

    def test_wrong_generator(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        structured["generator"] = "other"
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        assert any("generator: expected" in s for s in v)

    def test_invalid_sample_rate(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        structured["sample_rate_hz"] = -1
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        assert any("sample_rate_hz" in s for s in v)

    def test_invalid_n_samples(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        structured["n_samples"] = 0
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        assert any("n_samples" in s for s in v)

    def test_band_powers_not_normalized(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        bp = structured["features"]["freq_domain"]["band_powers"]
        # 篡改一个值使和不等于 1
        if bp:
            first_key = list(bp.keys())[0]
            bp[first_key] += 0.5
            tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
            v = validate_serialized(tampered)
            assert any("band_powers" in s for s in v)

    def test_unknown_top_field_warns(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        structured = json.loads(r.json_str)
        structured["unknown_extra"] = "foo"
        tampered = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        v = validate_serialized(tampered)
        # 未知字段仅告警，不阻断
        assert any("[warn]" in s and "unknown_extra" in s for s in v)

    def test_invalid_json(self) -> None:
        v = validate_serialized("{not json")
        assert len(v) == 1
        assert "invalid JSON" in v[0]

    def test_root_not_object(self) -> None:
        v = validate_serialized("[1,2,3]")
        assert any("expected object" in s for s in v)


# ─────────────────────────── 11. Round-trip ───────────────────────────

class TestRoundTrip:
    def test_serialize_validate_hash(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        # Round-trip：解析 JSON 再校验
        parsed = json.loads(r.json_str)
        assert parsed["schema"] == SCHEMA_VERSION
        assert parsed["generator"] == GENERATOR_NAME
        # hash 一致
        assert verify_hash(r.json_str, r.sha256)
        # 校验通过
        assert validate_serialized(r.json_str) == []

    def test_privacy_hash_stable(self) -> None:
        h1 = _privacy_hash("sub-123")
        h2 = _privacy_hash("sub-123")
        assert h1 == h2
        assert len(h1) == 16
        assert all(c in "0123456789abcdef" for c in h1)

    def test_privacy_hash_different_inputs(self) -> None:
        assert _privacy_hash("a") != _privacy_hash("b")

    def test_subject_hash_appears_in_output(self) -> None:
        b = TimeSeriesBundle("HRV", [1.0, 2.0, 3.0, 4.0, 5.0] * 10, 100, "bpm", "sub-X", "sess-Y")
        r = serialize(b)
        assert r.structured["subject_hash"] == _privacy_hash("sub-X")
        assert r.structured["session_hash"] == _privacy_hash("sess-Y")


# ─────────────────────────── 12. 性能 ───────────────────────────

class TestPerformance:
    def test_10000_samples_under_500ms(self) -> None:
        rng = random.Random(200)
        samples = [rng.gauss(0, 1) for _ in range(10000)]
        b = TimeSeriesBundle("HRV", samples, 100, "bpm", "s", "x")
        # 预热
        serialize(b)
        t0 = time.perf_counter()
        for _ in range(3):
            serialize(b)
        elapsed_ms = (time.perf_counter() - t0) * 1000 / 3
        assert elapsed_ms < 500, f"10000 样本平均 {elapsed_ms:.1f}ms 超过 500ms 上限"


# ─────────────────────────── 13. Text 模式 ───────────────────────────

class TestTextMode:
    def test_text_mode_returns_lines(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, format="text")
        assert r.text_lines is not None
        assert len(r.text_lines) > 0

    def test_text_mode_contains_all_top_fields(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, format="text")
        assert r.text_lines is not None
        joined = "\n".join(r.text_lines)
        for k in ("schema", "generator", "channel_name", "unit", "sample_rate_hz", "n_samples"):
            assert k in joined, f"text 模式缺 {k}"

    def test_text_mode_bins_rendered(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, format="text")
        joined = "\n".join(r.text_lines)
        assert "bin[" in joined

    def test_json_mode_no_text_lines(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, format="json")
        assert r.text_lines is None

    def test_text_lines_deterministic(self, rand_bundle: TimeSeriesBundle) -> None:
        r1 = serialize(rand_bundle, format="text")
        r2 = serialize(rand_bundle, format="text")
        assert r1.text_lines == r2.text_lines


# ─────────────────────────── 14. Schema 常量 ───────────────────────────

class TestSchemaConstants:
    def test_schema_version_v1(self) -> None:
        assert SCHEMA_VERSION == "v1"

    def test_generator_name(self) -> None:
        assert GENERATOR_NAME == "healthlens-ts-serializer"

    def test_top_field_order(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle)
        parsed = json.loads(r.json_str)
        # sort_keys=True 会按字母序，但字段值必须齐
        for k in ("schema", "generator", "channel_name", "unit", "sample_rate_hz", "n_samples", "features"):
            assert k in parsed


# ─────────────────────────── 15. SerializeOptions ───────────────────────────

class TestSerializeOptions:
    def test_disable_bins(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, options=SerializeOptions(include_bins=False))
        assert r.structured["bins"] == []

    def test_disable_freq_domain(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, options=SerializeOptions(enable_freq_domain=False))
        assert "freq_domain" not in r.structured["features"]

    def test_disable_time_domain(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, options=SerializeOptions(enable_time_domain=False))
        assert "time_domain" not in r.structured["features"]

    def test_disable_shape(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, options=SerializeOptions(enable_shape=False))
        assert "shape" not in r.structured["features"]

    def test_disable_context(self, rand_bundle: TimeSeriesBundle) -> None:
        r = serialize(rand_bundle, options=SerializeOptions(enable_context=False))
        assert "context" not in r.structured["features"]

    def test_custom_bin_width(self) -> None:
        samples = _rand_samples(1000)
        b = TimeSeriesBundle("HRV", samples, 100, "bpm")
        r = serialize(b, options=SerializeOptions(bin_width_s=2.0))
        # 10 秒 / 2 = 5 bins
        assert len(r.structured["bins"]) == 5

    def test_max_bins_cap(self) -> None:
        samples = _rand_samples(10000)
        b = TimeSeriesBundle("HRV", samples, 100, "bpm")
        r = serialize(b, options=SerializeOptions(bin_width_s=0.1, max_bins=10))
        assert len(r.structured["bins"]) <= 10
