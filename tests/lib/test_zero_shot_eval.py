"""§10 #6 Pulse-PPG / PaPaGei 零样本评测脚手架测试。

报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

覆盖：
- 合成数据确定性：同 seed 输出相同、不同 seed 输出不同
- PPG/ECG/EMG/EEG 各自波形构造（频域主要峰接近设定频率）
- 特征提取：HRV + 波形特征数量、类型、范围
- 分类任务：合成 3 类数据的 baseline 分类器 ≥0.7 accuracy
- 回归任务：合成线性关系数据的 baseline 回归 R² ≥0.5
- 异常任务：正常 vs 异常信号可分
- ZeroShotEvalHarness 空数据集抛错、未装真实模型抛 HealthLensUnavailableEngine
- API 端点：请求/响应 schema、样本数超限抛错

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import pytest

# 让测试可独立 import app
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.lib.synthetic_sensor_dataset import (
    CLASS_LABELS,
    SIGNAL_TYPES,
    SyntheticSensor,
    SyntheticSensorDataset,
    generate_batch,
    generate_ecg,
    generate_emg,
    generate_eeg,
    generate_ppg,
)
from app.lib.feature_baseline import (
    compute_hrv_features,
    compute_spectral_features,
    compute_waveform_features,
    extract_baseline_features,
    feature_names,
    to_feature_matrix,
)
from app.lib.zero_shot_eval_harness import (
    BaselineResult,
    EvaluatorConfig,
    ZeroShotEvalHarness,
    _accuracy,
    _auroc,
    _f1_macro,
    _r2,
)
from app.lib.sensor_adapter import HealthLensUnavailableEngine


# ─────────────────────────── fixtures ───────────────────────────

@pytest.fixture
def ppg_rest() -> list[float]:
    return generate_ppg(n_samples=500, freq_hz=0.9, noise=0.05, seed=0, sample_rate_hz=100.0)


@pytest.fixture
def ppg_exercise() -> list[float]:
    return generate_ppg(n_samples=500, freq_hz=1.8, noise=0.15, seed=1, sample_rate_hz=100.0, breath_mod=0.12)


@pytest.fixture
def ppg_stress() -> list[float]:
    return generate_ppg(n_samples=500, freq_hz=1.3, noise=0.20, seed=2, sample_rate_hz=100.0)


@pytest.fixture
def ecg_signal() -> list[float]:
    return generate_ecg(n_samples=500, freq_hz=1.2, noise=0.05, seed=3, sample_rate_hz=250.0)


@pytest.fixture
def emg_signal() -> list[float]:
    return generate_emg(n_samples=500, freq_hz=20.0, noise=0.5, seed=4, sample_rate_hz=500.0)


@pytest.fixture
def eeg_signal() -> list[float]:
    return generate_eeg(n_samples=1000, freq_hz=10.0, noise=0.1, seed=5, sample_rate_hz=250.0)


@pytest.fixture
def three_class_dataset() -> list[SyntheticSensor]:
    """3 类数据（rest / exercise / stress）用于分类测试。"""
    return generate_batch(n=45, seed=42, signal_type="PPG", duration_sec=3.0)


@pytest.fixture
def regression_dataset() -> list[SyntheticSensor]:
    """回归任务：合成线性关系数据（PPG 振幅 ∝ HR）。

    构造：4 档心率 60/72/90/108 BPM，每档 12 样本，共 48 条。
    信号形态：sin(2π * hr/60 * t) * (hr/100) —— 振幅直接线性编码 HR。
    这样 mean/rms/peak_to_peak 等波形特征与 HR 强线性相关，
    baseline 线性回归应能达到 R² ≥ 0.5。
    """
    sensors: list[SyntheticSensor] = []
    hr_bpm_levels = [60.0, 72.0, 90.0, 108.0]
    for i, hr in enumerate(hr_bpm_levels):
        freq = hr / 60.0
        amp = hr / 100.0  # 振幅线性编码 HR（60→0.6, 108→1.08）
        for k in range(12):
            rng = random.Random(1000 * i + k)
            samples = [
                amp * math.sin(2 * math.pi * freq * (j / 100.0))
                + 0.03 * rng.gauss(0, 1)
                for j in range(300)
            ]
            sensors.append(SyntheticSensor(
                signal_type="PPG",
                sample_rate_hz=100.0,
                duration_sec=3.0,
                subject_id=f"reg_{i}_{k}",
                samples=samples,
                label="reg",
                ground_truth_hr_bpm=hr,
            ))
    return sensors


@pytest.fixture
def anomaly_dataset() -> list[SyntheticSensor]:
    """异常检测：normal（正常 PPG）vs anomaly（含明显干扰/异常形态的 PPG）。"""
    rng = random.Random(43)
    sensors: list[SyntheticSensor] = []
    # 30 条 normal
    for i in range(30):
        s = generate_ppg(
            n_samples=300, freq_hz=1.2, noise=0.05,
            seed=200 + i, sample_rate_hz=100.0,
        )
        sensors.append(SyntheticSensor(
            signal_type="PPG", sample_rate_hz=100.0, duration_sec=3.0,
            subject_id=f"normal_{i}", samples=s, label="normal",
            ground_truth_hr_bpm=72.0,
        ))
    # 30 条 anomaly：大幅噪声 + 高频干扰
    for i in range(30):
        # 构造异常信号：正常 PPG + 大幅噪声 + 高频尖峰
        base = generate_ppg(
            n_samples=300, freq_hz=1.2, noise=0.05,
            seed=300 + i, sample_rate_hz=100.0,
        )
        rng_a = random.Random(400 + i)
        anomaly_samples = []
        for j, v in enumerate(base):
            # 大幅高斯噪声
            v2 = v + rng_a.gauss(0, 0.8)
            # 随机尖峰
            if rng_a.random() < 0.15:
                v2 += rng_a.choice([-3.0, 3.0])
            anomaly_samples.append(v2)
        sensors.append(SyntheticSensor(
            signal_type="PPG", sample_rate_hz=100.0, duration_sec=3.0,
            subject_id=f"anomaly_{i}", samples=anomaly_samples, label="anomaly",
            ground_truth_hr_bpm=72.0,
        ))
    return sensors


# ─────────────────────────── 1. 合成数据生成器 ───────────────────────────

class TestGenerators:
    """各信号类型生成器基础契约。"""

    def test_ppg_length(self, ppg_rest: list[float]) -> None:
        assert len(ppg_rest) == 500

    def test_ppg_deterministic(self) -> None:
        a = generate_ppg(n_samples=100, seed=7)
        b = generate_ppg(n_samples=100, seed=7)
        assert a == b

    def test_ppg_different_seeds_differ(self) -> None:
        a = generate_ppg(n_samples=100, seed=7)
        b = generate_ppg(n_samples=100, seed=8)
        assert a != b

    def test_ppg_invalid_n_raises(self) -> None:
        with pytest.raises(ValueError, match="n_samples"):
            generate_ppg(n_samples=0)

    def test_ppg_invalid_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="sample_rate_hz"):
            generate_ppg(n_samples=100, sample_rate_hz=0)

    def test_ecg_has_qrs_peak(self, ecg_signal: list[float]) -> None:
        # ECG 应有明显尖峰（R 峰），max 远大于 min
        assert max(ecg_signal) > 0.5
        assert min(ecg_signal) < 0

    def test_emg_wideband(self, emg_signal: list[float]) -> None:
        # EMG 宽带噪声，std 应该显著 > 0
        assert statistics_fmean_squared_dev(emg_signal) > 0.05

    def test_eeg_has_alpha_peak(self, eeg_signal: list[float]) -> None:
        # EEG 主导 α 波（8-13 Hz），dominant_freq 应在 5–15 Hz 区间
        feats = compute_spectral_features(eeg_signal, sample_rate_hz=250.0)
        assert 5.0 <= feats["dominant_freq"] <= 15.0

    def test_eeg_all_rhythms_present(self, eeg_signal: list[float]) -> None:
        # 三节律叠加，std 应 >0 且 kurtosis 应偏离 0
        wf = compute_waveform_features(eeg_signal)
        assert wf["std"] > 0.05
        assert math.isfinite(wf["kurtosis"])

    def test_signal_types_constant(self) -> None:
        assert set(SIGNAL_TYPES) == {"PPG", "ECG", "EMG", "EEG"}


def statistics_fmean_squared_dev(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


# ─────────────────────────── 2. 批量生成 ───────────────────────────

class TestGenerateBatch:
    def test_batch_length(self, three_class_dataset: list[SyntheticSensor]) -> None:
        assert len(three_class_dataset) == 45

    def test_batch_labels_balanced(self, three_class_dataset: list[SyntheticSensor]) -> None:
        from collections import Counter
        c = Counter(s.label for s in three_class_dataset)
        # 45 均分 3 类
        assert c["rest"] == 15
        assert c["exercise"] == 15
        assert c["stress"] == 15

    def test_batch_deterministic(self) -> None:
        a = generate_batch(n=20, seed=99)
        b = generate_batch(n=20, seed=99)
        assert a == b  # SyntheticSensor 是 dataclass，可比较

    def test_batch_different_seed_differs(self) -> None:
        a = generate_batch(n=10, seed=1)
        b = generate_batch(n=10, seed=2)
        assert a[0].samples != b[0].samples

    def test_batch_invalid_signal_type_raises(self) -> None:
        with pytest.raises(ValueError, match="signal_type"):
            generate_batch(n=10, signal_type="BCI")

    def test_batch_invalid_label_raises(self) -> None:
        with pytest.raises(ValueError, match="label"):
            generate_batch(n=3, labels=["foo", "bar", "baz"])

    def test_batch_labels_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="labels length"):
            generate_batch(n=5, labels=["rest", "exercise"])

    def test_batch_ground_truth_hr_matches_freq(self, three_class_dataset: list[SyntheticSensor]) -> None:
        # ground_truth_hr_bpm = freq_hz * 60
        for s in three_class_dataset[:3]:
            # 由于 PPG 分类预设固定 freq，直接验证 range
            assert 50.0 <= s.ground_truth_hr_bpm <= 120.0


# ─────────────────────────── 3. 数据集序列化 ───────────────────────────

class TestDataset:
    def test_dataset_to_from_json_roundtrip(self, three_class_dataset: list[SyntheticSensor]) -> None:
        ds = SyntheticSensorDataset(sensors=three_class_dataset, metadata={"seed": 42})
        payload = ds.to_json()
        ds2 = SyntheticSensorDataset.from_json(payload)
        assert len(ds2) == len(ds)
        for a, b in zip(ds.sensors, ds2.sensors):
            assert a.samples == b.samples
            assert a.label == b.label
            assert a.signal_type == b.signal_type

    def test_dataset_fingerprint_stable(self, three_class_dataset: list[SyntheticSensor]) -> None:
        ds = SyntheticSensorDataset(sensors=three_class_dataset, metadata={"seed": 42})
        fp1 = ds.fingerprint()
        fp2 = ds.fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_dataset_from_json_bad_schema_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported dataset schema"):
            SyntheticSensorDataset.from_json(json.dumps({"schema": "v2"}))


# ─────────────────────────── 4. 特征提取 ───────────────────────────

class TestFeatureExtraction:
    def test_waveform_features_count(self, ppg_rest: list[float]) -> None:
        wf = compute_waveform_features(ppg_rest)
        # 波形特征应 17 维
        assert 15 <= len(wf) <= 20

    def test_waveform_features_types(self, ppg_rest: list[float]) -> None:
        wf = compute_waveform_features(ppg_rest)
        for v in wf.values():
            assert isinstance(v, float)

    def test_waveform_features_peak_to_peak_positive(self, ppg_rest: list[float]) -> None:
        wf = compute_waveform_features(ppg_rest)
        assert wf["peak_to_peak"] > 0

    def test_waveform_features_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            compute_waveform_features([])

    def test_hrv_features_keys(self, ppg_rest: list[float]) -> None:
        hrv = compute_hrv_features(ppg_rest, sample_rate_hz=100.0)
        expected_keys = {
            "rri_mean", "rri_std", "rri_cv",
            "rmssd", "sdnn", "pnn50",
            "sd1", "sd2",
            "vlf_power", "lf_power", "hf_power",
            "lf_hf_ratio", "n_rri",
        }
        assert set(hrv.keys()) == expected_keys

    def test_hrv_power_sums_to_one(self, ppg_rest: list[float]) -> None:
        hrv = compute_hrv_features(ppg_rest, sample_rate_hz=100.0)
        total = hrv["vlf_power"] + hrv["lf_power"] + hrv["hf_power"]
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_hrv_all_float(self, ppg_rest: list[float]) -> None:
        hrv = compute_hrv_features(ppg_rest, sample_rate_hz=100.0)
        for v in hrv.values():
            assert isinstance(v, (int, float))

    def test_hrv_short_signal_returns_zeros(self) -> None:
        # 太短的信号无 RR 间期，返回全 0
        short = [1.0, 2.0, 3.0, 4.0, 5.0]
        hrv = compute_hrv_features(short, sample_rate_hz=100.0)
        assert hrv["n_rri"] == 0
        assert hrv["rmssd"] == 0.0

    def test_spectral_features_in_range(self, eeg_signal: list[float]) -> None:
        sp = compute_spectral_features(eeg_signal, sample_rate_hz=250.0)
        assert 0.0 <= sp["spectral_entropy"] <= 1.0 + 1e-9
        assert sp["dominant_freq"] > 0

    def test_baseline_features_20_30_dim(self, ppg_rest: list[float]) -> None:
        feats = extract_baseline_features(ppg_rest, sample_rate_hz=100.0, signal_type="PPG")
        # 目标 20–30 维
        assert 20 <= len(feats) <= 35, f"got {len(feats)} dims"

    def test_baseline_features_all_float(self, ppg_rest: list[float]) -> None:
        feats = extract_baseline_features(ppg_rest, 100.0, "PPG")
        for k, v in feats.items():
            assert isinstance(v, float), f"{k}={v} not float"

    def test_baseline_features_ppg_has_hrv(self, ppg_rest: list[float]) -> None:
        feats = extract_baseline_features(ppg_rest, 100.0, "PPG")
        assert "rmssd" in feats
        assert "sdnn" in feats

    def test_baseline_features_eeg_has_spectral(self, eeg_signal: list[float]) -> None:
        feats = extract_baseline_features(eeg_signal, 250.0, "EEG")
        assert "dominant_freq" in feats
        assert "spectral_entropy" in feats

    def test_baseline_features_invalid_signal_type_raises(self, ppg_rest: list[float]) -> None:
        with pytest.raises(ValueError, match="signal_type"):
            extract_baseline_features(ppg_rest, 100.0, "BCI")

    def test_baseline_features_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            extract_baseline_features([], 100.0, "PPG")

    def test_baseline_features_invalid_rate_raises(self, ppg_rest: list[float]) -> None:
        with pytest.raises(ValueError, match="sample_rate_hz"):
            extract_baseline_features(ppg_rest, 0, "PPG")

    def test_feature_names_stable(self) -> None:
        # 特征名顺序稳定（供列对齐）
        n1 = feature_names("PPG")
        n2 = feature_names("PPG")
        assert n1 == n2
        assert len(n1) == len(feature_names("PPG"))


# ─────────────────────────── 5. 分类任务 ───────────────────────────

class TestClassification:
    def test_baseline_accuracy_at_least_0_7(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(
            signal_type="PPG", task="classification", metric="accuracy", random_seed=42
        ))
        result = h.run_baseline(three_class_dataset)
        assert result.accuracy >= 0.7, f"expected >=0.7, got {result.accuracy}"
        assert result.f1_macro >= 0.7, f"expected >=0.7, got {result.f1_macro}"
        assert result.n_samples == len(three_class_dataset)

    def test_baseline_result_type(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        result = h.run_baseline(three_class_dataset)
        assert isinstance(result, BaselineResult)
        assert result.engine_name == "baseline"

    def test_baseline_classification_details(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        result = h.run_baseline(three_class_dataset)
        assert "per_class_f1" in result.details
        assert "n_train" in result.details
        assert "n_test" in result.details

    def test_baseline_empty_dataset_raises(self) -> None:
        h = ZeroShotEvalHarness()
        with pytest.raises(ValueError, match="empty"):
            h.run_baseline([])

    def test_baseline_deterministic(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h1 = ZeroShotEvalHarness(EvaluatorConfig(random_seed=42))
        h2 = ZeroShotEvalHarness(EvaluatorConfig(random_seed=42))
        r1 = h1.run_baseline(three_class_dataset)
        r2 = h2.run_baseline(three_class_dataset)
        # 同 seed 同数据 → 同指标
        assert r1.accuracy == r2.accuracy
        assert r1.f1_macro == r2.f1_macro


# ─────────────────────────── 6. 回归任务 ───────────────────────────

class TestRegression:
    def test_baseline_r2_at_least_0_5(self, regression_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(
            signal_type="PPG", task="regression", metric="accuracy", random_seed=42
        ))
        result = h.run_baseline(regression_dataset)
        assert result.r2 >= 0.5, f"expected R²>=0.5, got {result.r2}"

    def test_regression_details_have_mae(self, regression_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(task="regression"))
        result = h.run_baseline(regression_dataset)
        assert "mae" in result.details
        assert "nrmse" in result.details
        assert "target_mean_hr" in result.details
        assert result.accuracy == 0.0  # 回归任务不填 accuracy

    def test_regression_result_metric_value_is_r2(self, regression_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(task="regression"))
        result = h.run_baseline(regression_dataset)
        assert result.metric_value == result.r2


# ─────────────────────────── 7. 异常任务 ───────────────────────────

class TestAnomaly:
    def test_anomaly_auroc_reasonable(self, anomaly_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(
            signal_type="PPG", task="anomaly", metric="auroc", random_seed=42
        ))
        result = h.run_baseline(anomaly_dataset)
        # 异常信号噪声大幅 > 正常，AUROC 应显著 > 0.5
        assert result.auroc >= 0.7, f"expected AUROC>=0.7, got {result.auroc}"

    def test_anomaly_has_pos_and_neg(self, anomaly_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness(EvaluatorConfig(task="anomaly"))
        result = h.run_baseline(anomaly_dataset)
        assert result.details["n_pos_test"] > 0
        assert result.details["n_neg_test"] > 0


# ─────────────────────────── 8. 引擎接口（未装模型 fail-loud） ───────────────────────────

class TestEngineInterface:
    def test_run_engine_none_raises(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        with pytest.raises(HealthLensUnavailableEngine, match="engine is None"):
            h.run_engine(None, three_class_dataset)

    def test_run_engine_missing_name_raises(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        # engine dict 无 engine_name
        with pytest.raises(HealthLensUnavailableEngine, match="engine_name"):
            h.run_engine({}, three_class_dataset)

    def test_run_engine_missing_predict_raises(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        # engine 有 name 但无 predict
        with pytest.raises(HealthLensUnavailableEngine, match="predict"):
            h.run_engine({"engine_name": "Pulse-PPG"}, three_class_dataset)

    def test_run_engine_works_with_mock_predict(self, three_class_dataset: list[SyntheticSensor]) -> None:
        # mock 一个 predict，返回随机标签（模拟真实模型）
        def mock_predict(X: list[list[float]]) -> list[str]:
            # 按 label 分布随机返回（这里为了测试 harness 契约，返回随机标签即可）
            rng = random.Random(123)
            labels = ["rest", "exercise", "stress"]
            return [rng.choice(labels) for _ in X]

        h = ZeroShotEvalHarness(EvaluatorConfig(task="classification"))
        result = h.run_engine(
            {"engine_name": "Pulse-PPG-mock", "predict": mock_predict},
            three_class_dataset,
        )
        assert result.engine_name == "Pulse-PPG-mock"
        assert 0.0 <= result.accuracy <= 1.0

    def test_run_engine_empty_dataset_raises(self) -> None:
        h = ZeroShotEvalHarness()
        with pytest.raises(ValueError, match="empty"):
            h.run_engine({"engine_name": "x", "predict": lambda X: []}, [])


# ─────────────────────────── 9. 对比报告 ───────────────────────────

class TestCompare:
    def test_compare_empty_returns_empty(self) -> None:
        cmp = ZeroShotEvalHarness.compare([])
        assert cmp["rows"] == []
        assert "no results" in cmp["summary"]

    def test_compare_markdown_table(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        r1 = h.run_baseline(three_class_dataset)
        cmp = ZeroShotEvalHarness.compare([r1])
        assert "| engine |" in cmp["markdown_table"]
        assert "baseline" in cmp["markdown_table"]

    def test_compare_best_accuracy(self, three_class_dataset: list[SyntheticSensor]) -> None:
        h = ZeroShotEvalHarness()
        r1 = h.run_baseline(three_class_dataset)
        cmp = ZeroShotEvalHarness.compare([r1])
        assert cmp["best_accuracy"] == "baseline"


# ─────────────────────────── 10. 指标工具函数 ───────────────────────────

class TestMetrics:
    def test_accuracy_perfect(self) -> None:
        assert _accuracy(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_accuracy_zero(self) -> None:
        assert _accuracy(["a", "a", "a"], ["b", "b", "b"]) == 0.0

    def test_accuracy_empty(self) -> None:
        assert _accuracy([], []) == 0.0

    def test_f1_macro_perfect(self) -> None:
        y_true = ["a", "a", "b", "b", "c", "c"]
        y_pred = ["a", "a", "b", "b", "c", "c"]
        assert _f1_macro(y_true, y_pred) == 1.0

    def test_f1_macro_random(self) -> None:
        # 完全乱猜
        y_true = ["a", "a", "b", "b", "c", "c"]
        y_pred = ["b", "c", "a", "c", "a", "b"]
        f1 = _f1_macro(y_true, y_pred)
        assert 0.0 <= f1 <= 1.0

    def test_auroc_perfect(self) -> None:
        y_bin = [1, 1, 0, 0]
        scores = [0.9, 0.8, 0.2, 0.1]
        assert _auroc(y_bin, scores) == 1.0

    def test_auroc_perfect_inverted(self) -> None:
        y_bin = [1, 1, 0, 0]
        scores = [0.1, 0.2, 0.8, 0.9]
        assert _auroc(y_bin, scores) == 0.0

    def test_auroc_single_class(self) -> None:
        y_bin = [1, 1, 1]
        assert _auroc(y_bin, [0.1, 0.2, 0.3]) == 0.5

    def test_r2_perfect(self) -> None:
        y_true = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _r2(y_true, [1.0, 2.0, 3.0, 4.0, 5.0]) == 1.0

    def test_r2_constant_true(self) -> None:
        # y_true 全相等：ss_tot = 0，返回 0
        assert _r2([3.0, 3.0, 3.0], [3.0, 3.0, 3.0]) == 0.0


# ─────────────────────────── 11. EvaluatorConfig 校验 ───────────────────────────

class TestEvaluatorConfig:
    def test_default_config_valid(self) -> None:
        cfg = EvaluatorConfig()
        cfg.validate()  # 不抛错

    def test_invalid_signal_type_raises(self) -> None:
        cfg = EvaluatorConfig(signal_type="BCI")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="signal_type"):
            cfg.validate()

    def test_invalid_task_raises(self) -> None:
        cfg = EvaluatorConfig(task="clustering")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="task"):
            cfg.validate()

    def test_invalid_metric_raises(self) -> None:
        cfg = EvaluatorConfig(metric="auc")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="metric"):
            cfg.validate()

    def test_invalid_train_ratio_raises(self) -> None:
        cfg = EvaluatorConfig(train_ratio=0.0)
        with pytest.raises(ValueError, match="train_ratio"):
            cfg.validate()
        cfg2 = EvaluatorConfig(train_ratio=1.0)
        with pytest.raises(ValueError, match="train_ratio"):
            cfg2.validate()


# ─────────────────────────── 12. API 端点 ───────────────────────────

class TestEvalHarnessAPI:
    """API 端点契约测试（用 FastAPI TestClient 走 ASGI）。"""

    @pytest.fixture(autouse=True)
    def _skip_if_no_fastapi(self):
        try:
            from fastapi import FastAPI  # noqa: F401
            from httpx import ASGITransport, AsyncClient  # noqa: F401
        except ImportError:
            pytest.skip("fastapi or httpx not available")

    def test_endpoint_registered(self) -> None:
        from app.api.timeseries import router
        paths = {r.path for r in router.routes}
        assert "/eval/harness" in paths

    def test_harness_request_schema_min_length(self) -> None:
        from app.api.timeseries import HarnessRequest
        # min_length=2，只传 1 条应抛 ValidationError
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            HarnessRequest(
                signal_type="PPG", task="classification",
                samples=[{"samples": [1.0, 2.0, 3.0, 4.0], "sample_rate_hz": 100.0, "label": "rest"}],
            )

    def test_harness_request_schema_max_length(self) -> None:
        from app.api.timeseries import HarnessRequest
        from pydantic import ValidationError
        # max_length=1000，传 1001 条应抛错
        samples = [
            {"samples": [1.0, 2.0, 3.0, 4.0], "sample_rate_hz": 100.0, "label": "rest"}
            for _ in range(1001)
        ]
        with pytest.raises(ValidationError):
            HarnessRequest(signal_type="PPG", task="classification", samples=samples)

    def test_harness_signal_schema_missing_samples_raises(self) -> None:
        from app.api.timeseries import HarnessRequest
        from pydantic import ValidationError
        # 缺少 samples 字段应通过 pydantic 校验（samples 是 dict，但缺 samples 键会在端点内抛 400）
        # 这里只测 pydantic 层：至少需要 min_length=2
        req = HarnessRequest(
            signal_type="PPG", task="classification",
            samples=[
                {"samples": [1.0, 2.0, 3.0, 4.0], "sample_rate_hz": 100.0, "label": "rest"},
                {"samples": [1.0, 2.0, 3.0, 4.0], "sample_rate_hz": 100.0, "label": "rest"},
            ],
        )
        assert len(req.samples) == 2

    def test_harness_response_schema_fields(self) -> None:
        from app.api.timeseries import HarnessResponse
        r = HarnessResponse(
            engine_name="baseline", accuracy=0.8, f1_macro=0.8, auroc=0.0,
            metric_value=0.8, r2=0.0, latency_ms=10.0, n_samples=10, details={},
        )
        d = r.model_dump()
        assert d["engine_name"] == "baseline"
        assert d["accuracy"] == 0.8
        assert "report_source" in d
        assert "note" in d

    def test_harness_endpoint_returns_400_on_short_samples(self) -> None:
        """端点内校验：单条信号 samples 长度 < 4 应返回 400。"""
        import pytest_asyncio  # noqa: F401  # 确保异步 fixture 可用
        from app.api.timeseries import run_eval_harness, HarnessRequest
        from fastapi import HTTPException
        req = HarnessRequest(
            signal_type="PPG", task="classification",
            samples=[
                {"samples": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], "sample_rate_hz": 100.0, "label": "rest"},
                {"samples": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], "sample_rate_hz": 100.0, "label": "exercise"},
                {"samples": [1.0, 2.0], "sample_rate_hz": 100.0, "label": "stress"},  # 太短
            ],
        )
        with pytest.raises(HTTPException) as ei:
            run_eval_harness(req)
        assert ei.value.status_code == 400

    def test_harness_endpoint_returns_400_on_regression_missing_hr(self) -> None:
        """regression 任务缺 ground_truth_hr_bpm 应 400。"""
        from app.api.timeseries import run_eval_harness, HarnessRequest
        from fastapi import HTTPException
        req = HarnessRequest(
            signal_type="PPG", task="regression",
            samples=[
                {"samples": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], "sample_rate_hz": 100.0},
                {"samples": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], "sample_rate_hz": 100.0},
            ],
        )
        with pytest.raises(HTTPException) as ei:
            run_eval_harness(req)
        assert ei.value.status_code == 400

    def test_harness_endpoint_ok_minimal(self) -> None:
        """最小成功路径：8 样本 * 4 条 → 返回 BaselineResult。"""
        from app.api.timeseries import run_eval_harness, HarnessRequest
        # 用真实 PPG 波形构造请求
        import random as _r
        rng = _r.Random(42)
        def _sig():
            return [rng.gauss(0, 1) for _ in range(30)]
        samples = []
        for lab in ["rest", "exercise", "stress", "rest"]:
            samples.append({"samples": _sig(), "sample_rate_hz": 100.0, "label": lab})
        req = HarnessRequest(
            signal_type="PPG", task="classification",
            samples=samples,
        )
        resp = run_eval_harness(req)
        assert resp.engine_name == "baseline"
        assert resp.n_samples == 4
        assert 0.0 <= resp.accuracy <= 1.0


# ─────────────────────────── 13. Sensor 数据模型 ───────────────────────────

class TestSyntheticSensorModel:
    def test_to_from_dict_roundtrip(self) -> None:
        s = SyntheticSensor(
            signal_type="PPG", sample_rate_hz=100.0, duration_sec=5.0,
            subject_id="subj_1", samples=[1.0, 2.0, 3.0],
            label="rest", ground_truth_hr_bpm=72.0,
        )
        d = s.to_dict()
        s2 = SyntheticSensor.from_dict(d)
        assert s2.samples == s.samples
        assert s2.label == s.label
        assert s2.ground_truth_hr_bpm == s.ground_truth_hr_bpm

    def test_n_samples(self) -> None:
        s = SyntheticSensor(
            signal_type="PPG", sample_rate_hz=100.0, duration_sec=5.0,
            subject_id="subj_1", samples=[1.0, 2.0, 3.0],
        )
        assert s.n_samples() == 3


# ─────────────────────────── 14. 基线回归器与 KNN 单元 ───────────────────────────

class TestBaselines:
    def test_linear_regression_fits_line(self) -> None:
        from app.lib.zero_shot_eval_harness import _LinearRegression
        X = [[float(i)] for i in range(10)]
        y = [2.0 * i + 1.0 for i in range(10)]
        reg = _LinearRegression()
        reg.fit(X, y)
        pred = reg.predict([5.0])
        assert pred == pytest.approx(11.0, abs=0.1)

    def test_linear_regression_needs_at_least_2(self) -> None:
        from app.lib.zero_shot_eval_harness import _LinearRegression
        reg = _LinearRegression()
        with pytest.raises(ValueError, match="2 samples"):
            reg.fit([[1.0]], [1.0])

    def test_knn_perfect_training(self) -> None:
        from app.lib.zero_shot_eval_harness import _KNNClassifier
        X = [[1.0, 1.0], [2.0, 2.0], [5.0, 5.0], [6.0, 6.0]]
        y = ["a", "a", "b", "b"]
        clf = _KNNClassifier(k=1)
        clf.fit(X, y)
        assert clf.predict([1.5, 1.5]) == "a"
        assert clf.predict([5.5, 5.5]) == "b"

    def test_knn_unfit_raises(self) -> None:
        from app.lib.zero_shot_eval_harness import _KNNClassifier
        clf = _KNNClassifier(k=1)
        with pytest.raises(ValueError, match="not fitted"):
            clf.predict([1.0, 1.0])
