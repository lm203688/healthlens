"""特征工程 baseline（对标 Pulse-PPG / PaPaGei 的手工特征）

报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

本模块实现 baseline 手工特征提取器，作为 Pulse-PPG / PaPaGei 真实模型的
对照。设计原则：
- **纯 Python**：不引 numpy/scipy/sklearn；用 statistics + math 实现。
- **20–30 维特征**：覆盖时域（HRV + 波形）+ 频域（多带功率）+ 时序相关。
- **按 signal_type 路由**：PPG 用 HRV，ECG 用波形，EMG/EEG 用节律相关。
- **不重复 pulse_engine**：pulse_engine 是脉象知识库规则判定；本模块
  输出**数值特征向量**（供分类器/回归器消费），二者是互补而非覆盖。

Wellness 平台术语纪律：仅产出统计表征，不诊断。
"""
from __future__ import annotations

import math
import statistics
from typing import Any


# ─────────────────────────── HRV 特征 ───────────────────────────

def _peak_intervals_ppg(samples: list[float]) -> list[float]:
    """简易心搏间隔估计（RR 间期秒）。

    算法：找连续局部极大值（> 邻域均值），返回相邻峰的时间差。
    非医学级精度，仅评测 baseline 用。
    """
    n = len(samples)
    if n < 4:
        return []
    # 一阶差分找局部极大
    peaks: list[int] = []
    for i in range(1, n - 1):
        if samples[i] > samples[i - 1] and samples[i] > samples[i + 1]:
            peaks.append(i)
    # 相邻峰间隔（避免连续两个峰太近，过滤 <20% 平均间隔的假峰）
    if len(peaks) < 2:
        return []
    intervals_raw = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
    if not intervals_raw:
        return []
    mean_iv = statistics.fmean(intervals_raw)
    min_iv = mean_iv * 0.2
    filtered = [iv for iv in intervals_raw if iv >= min_iv]
    return filtered


def _band_power_dft(
    values: list[float],
    sample_rate_hz: float,
    f_lo: float,
    f_hi: float,
) -> float:
    """在 [f_lo, f_hi] 频带的功率（简化 DFT 中心频率采样）。"""
    n = len(values)
    if n < 4 or f_hi <= f_lo:
        return 0.0
    m = statistics.fmean(values)
    x = [v - m for v in values]
    f_center = (f_lo + f_hi) / 2.0
    cos_c = 0.0
    sin_c = 0.0
    for i, v in enumerate(x):
        angle = 2 * math.pi * f_center * i / sample_rate_hz
        cos_c += v * math.cos(angle)
        sin_c += v * math.sin(angle)
    return (cos_c ** 2 + sin_c ** 2) / (2.0 * n)


def compute_hrv_features(samples: list[float], sample_rate_hz: float) -> dict[str, float]:
    """计算 HRV 特征（基于 PPG 心搏间隔近似）。

    返回键（全部为 float）：
    - rri_mean / rri_std / rri_cv：间期统计
    - rmssd：相邻间期差值平方和的均方根
    - sdnn：间期标准差（近似 rri_std）
    - pnn50：相邻差 > 50ms 的比例
    - sd1 / sd2：Poincaré 图两点差/两点均的离散度
    - vlf_power / lf_power / hf_power：频带功率（相对归一化）
    - lf_hf_ratio：LF/HF 比
    """
    rri_samples = _peak_intervals_ppg(samples)
    rri_seconds: list[float] = [iv / sample_rate_hz for iv in rri_samples]

    if len(rri_seconds) < 3:
        # 无法估算 HRV 时返回全 0（fail-loud 由调用方决定）
        return {
            "rri_mean": 0.0, "rri_std": 0.0, "rri_cv": 0.0,
            "rmssd": 0.0, "sdnn": 0.0, "pnn50": 0.0,
            "sd1": 0.0, "sd2": 0.0,
            "vlf_power": 0.0, "lf_power": 0.0, "hf_power": 0.0,
            "lf_hf_ratio": 0.0,
            "n_rri": 0,
        }

    mean = statistics.fmean(rri_seconds)
    sdnn = statistics.pstdev(rri_seconds) if len(rri_seconds) > 1 else 0.0
    diffs = [abs(rri_seconds[i] - rri_seconds[i - 1]) for i in range(1, len(rri_seconds))]
    rmssd = math.sqrt(statistics.fmean(d * d for d in diffs)) if diffs else 0.0
    pnn50 = sum(1 for d in diffs if d > 0.05) / len(diffs) if diffs else 0.0
    cv = (sdnn / mean) if mean > 1e-9 else 0.0

    # Poincaré SD1/SD2（近似）
    d_x = [rri_seconds[i] for i in range(len(rri_seconds) - 1)]
    d_y = [rri_seconds[i + 1] for i in range(len(rri_seconds) - 1)]
    mx = statistics.fmean(d_x) if d_x else 0.0
    my = statistics.fmean(d_y) if d_y else 0.0
    sd1_sq = 0.0
    sd2_sq = 0.0
    for i in range(len(d_x)):
        dx = d_x[i] - mx
        dy = d_y[i] - my
        sd1_sq += (dy - dx) ** 2
        sd2_sq += (dy + dx) ** 2
    sd1 = math.sqrt(sd1_sq / (2 * len(d_x))) if d_x else 0.0
    sd2 = math.sqrt(sd2_sq / (2 * len(d_x))) if d_x else 0.0

    # 频带功率：VLF (<0.04) / LF (0.04–0.15) / HF (0.15–0.4)
    # 注意：HRV 分析在 HR 域，但此处用原始样本做粗略频段估计，仅 baseline 用。
    vlf = _band_power_dft(samples, sample_rate_hz, 0.0, 0.04)
    lf = _band_power_dft(samples, sample_rate_hz, 0.04, 0.15)
    hf = _band_power_dft(samples, sample_rate_hz, 0.15, 0.4)
    total = vlf + lf + hf
    if total > 1e-18:
        vlf_n, lf_n, hf_n = vlf / total, lf / total, hf / total
    else:
        vlf_n, lf_n, hf_n = 0.0, 0.0, 0.0
    lf_hf_ratio = (lf / hf) if hf > 1e-18 else 0.0

    return {
        "rri_mean": round(mean, 6),
        "rri_std": round(sdnn, 6),
        "rri_cv": round(cv, 6),
        "rmssd": round(rmssd, 6),
        "sdnn": round(sdnn, 6),
        "pnn50": round(pnn50, 6),
        "sd1": round(sd1, 6),
        "sd2": round(sd2, 6),
        "vlf_power": round(vlf_n, 6),
        "lf_power": round(lf_n, 6),
        "hf_power": round(hf_n, 6),
        "lf_hf_ratio": round(lf_hf_ratio, 6),
        "n_rri": float(len(rri_seconds)),
    }


# ─────────────────────────── 波形特征 ───────────────────────────

def compute_waveform_features(samples: list[float]) -> dict[str, float]:
    """计算波形统计特征（时域 + 形状）。

    返回键：
    - mean / std / rms / mad：一阶二阶
    - min / max / peak_to_peak
    - cv：变异系数
    - skew / kurt：三/四阶矩
    - rise_time：最大上升沿斜率倒数（秒，粗略）
    - zero_crossing_rate：去均值后零穿越率
    - lag1_ac / lag2_ac / lag3_ac：自相关
    - monotonic_fraction：单调相邻比例
    - endpoint_slope：端点差分斜率
    """
    n = len(samples)
    if n == 0:
        raise ValueError("samples must be non-empty")
    m = statistics.fmean(samples)
    s = statistics.pstdev(samples) if n > 1 else 0.0
    rms = math.sqrt(statistics.fmean(v * v for v in samples))
    mad = statistics.fmean(abs(v - m) for v in samples)
    mn, mx = min(samples), max(samples)
    cv = (s / m) if abs(m) > 1e-12 else 0.0
    p2p = mx - mn

    # skew / kurtosis
    if n >= 3 and s > 1e-12:
        m3 = statistics.fmean((v - m) ** 3 for v in samples)
        m4 = statistics.fmean((v - m) ** 4 for v in samples)
        skew = m3 / (s ** 3)
        kurt = (m4 / (s ** 4)) - 3.0
    else:
        skew = 0.0
        kurt = 0.0

    # rise_time：找最大正差分
    max_diff = 0.0
    for i in range(1, n):
        d = samples[i] - samples[i - 1]
        if d > max_diff:
            max_diff = d
    rise_time = (1.0 / max_diff) if max_diff > 1e-12 else 0.0

    # zero crossing rate
    zc = 0
    for i in range(1, n):
        if (samples[i - 1] - m) * (samples[i] - m) < 0:
            zc += 1
    zcr = zc / (n - 1) if n > 1 else 0.0

    # autocorrelation lag 1/2/3
    def _ac(lag: int) -> float:
        if n < lag + 2:
            return 0.0
        m1 = statistics.fmean(samples[:n - lag])
        m2 = statistics.fmean(samples[lag:])
        x1 = [v - m1 for v in samples[:n - lag]]
        x2 = [v - m2 for v in samples[lag:]]
        n_ = len(x1)
        if n_ == 0:
            return 0.0
        s1 = statistics.pstdev(x1)
        s2 = statistics.pstdev(x2)
        if s1 < 1e-12 or s2 < 1e-12:
            return 0.0
        cov = statistics.fmean(x1[i] * x2[i] for i in range(n_)) - statistics.fmean(x1) * statistics.fmean(x2)
        return cov / (s1 * s2)

    ac1 = _ac(1)
    ac2 = _ac(2)
    ac3 = _ac(3)

    # monotonic fraction
    if n >= 3:
        signs = [1 if samples[i] - samples[i - 1] > 0 else (-1 if samples[i] - samples[i - 1] < 0 else 0) for i in range(1, n)]
        same = sum(1 for i in range(1, len(signs)) if signs[i] == signs[i - 1] and signs[i] != 0)
        mono = same / (len(signs) - 1) if len(signs) > 1 else 0.0
    else:
        mono = 0.0

    endpoint_slope = (samples[-1] - samples[0]) if n >= 2 else 0.0

    return {
        "mean": round(m, 6),
        "std": round(s, 6),
        "rms": round(rms, 6),
        "mad": round(mad, 6),
        "min": round(mn, 6),
        "max": round(mx, 6),
        "peak_to_peak": round(p2p, 6),
        "cv": round(cv, 6),
        "skew": round(skew, 6),
        "kurtosis": round(kurt, 6),
        "rise_time": round(rise_time, 6),
        "zero_crossing_rate": round(zcr, 6),
        "lag1_autocorr": round(ac1, 6),
        "lag2_autocorr": round(ac2, 6),
        "lag3_autocorr": round(ac3, 6),
        "monotonic_fraction": round(mono, 6),
        "endpoint_slope": round(endpoint_slope, 6),
    }


# ─────────────────────────── 频域特征（EEG/EMG 通用） ───────────────────────────

def _band_powers_normalized(
    samples: list[float],
    sample_rate_hz: float,
    bands: list[tuple[float, float]],
) -> dict[str, float]:
    """多频带归一化功率。"""
    raw: list[float] = []
    for f_lo, f_hi in bands:
        raw.append(_band_power_dft(samples, sample_rate_hz, f_lo, f_hi))
    total = sum(raw)
    if total <= 1e-18:
        return {f"band_power_{f_lo}_{f_hi}": 0.0 for f_lo, f_hi in bands}
    return {f"band_power_{f_lo}_{f_hi}": round(r / total, 6) for r, (f_lo, f_hi) in zip(raw, bands)}


def compute_spectral_features(samples: list[float], sample_rate_hz: float) -> dict[str, float]:
    """通用频域特征：多频带功率 + 主频 + 谱熵。

    用于 EEG（α/β/θ）和 EMG（宽频）：
    - EEG: θ(4–8), α(8–13), β(13–30)
    - EMG: 20–50, 50–100, 100–250
    """
    n = len(samples)
    if n < 4:
        return {"dominant_freq": 0.0, "spectral_entropy": 0.0}
    m = statistics.fmean(samples)
    x = [v - m for v in samples]
    nyquist = sample_rate_hz / 2.0
    if nyquist < 0.05:
        return {"dominant_freq": 0.0, "spectral_entropy": 0.0}
    # 对数等间隔 32 点
    n_f = 32
    f_lo = max(0.01, nyquist / 100.0)
    f_hi = nyquist * 0.99
    log_lo, log_hi = math.log(f_lo), math.log(f_hi)
    step = (log_hi - log_lo) / (n_f - 1)
    freqs = [math.exp(log_lo + i * step) for i in range(n_f)]
    powers: list[float] = []
    for f in freqs:
        cos_c = 0.0
        sin_c = 0.0
        for i, v in enumerate(x):
            angle = 2 * math.pi * f * i / sample_rate_hz
            cos_c += v * math.cos(angle)
            sin_c += v * math.sin(angle)
        p = (cos_c ** 2 + sin_c ** 2) / (2.0 * n) if n > 0 else 0.0
        powers.append(p)
    total = sum(powers)
    if total <= 1e-18:
        return {"dominant_freq": 0.0, "spectral_entropy": 0.0}
    norm = [p / total for p in powers]
    max_i = max(range(n_f), key=lambda i: norm[i])
    dom_freq = freqs[max_i]
    entropy = -sum(p * math.log2(p) for p in norm if p > 0)
    max_ent = math.log2(n_f) if n_f > 1 else 1.0
    return {
        "dominant_freq": round(dom_freq, 6),
        "spectral_entropy": round(entropy / max_ent if max_ent > 0 else 0.0, 6),
    }


# ─────────────────────────── 按 signal_type 路由 ───────────────────────────

def _select_feature_groups(signal_type: str) -> tuple[list[str], list[tuple[float, float]]]:
    """按信号类型返回 (feature_group, band_specs)。

    - PPG: HRV + waveform（心率/波形）
    - ECG: waveform（波形形态）+ HRV 近似（QRS 间隔）
    - EMG: waveform + spectral（20–50 / 50–100 / 100–250 Hz）
    - EEG: spectral（θ / α / β）+ waveform
    """
    if signal_type == "PPG":
        return ("hrv", "waveform"), [(0.0, 0.04), (0.04, 0.15), (0.15, 0.4)]
    if signal_type == "ECG":
        return ("waveform", "hrv"), [(0.0, 0.5), (0.5, 5.0), (5.0, 25.0)]
    if signal_type == "EMG":
        return ("waveform", "spectral"), [(20.0, 50.0), (50.0, 100.0), (100.0, 250.0)]
    if signal_type == "EEG":
        return ("waveform", "spectral"), [(4.0, 8.0), (8.0, 13.0), (13.0, 30.0)]
    raise ValueError(f"unknown signal_type: {signal_type!r}")


def extract_baseline_features(
    samples: list[float],
    sample_rate_hz: float,
    signal_type: str,
) -> dict[str, float]:
    """按 signal_type 提取 baseline 特征（目标 20–30 维）。

    返回一个 dict[str, float]（键顺序稳定，供分类器消费）。
    特征总数通常 26–32 维，覆盖：
    - 时域波形（16 维，共用于所有信号类型）
    - HRV（13 维，PPG / ECG 用）或频带功率（3 维，EMG / EEG 用）
    - 频域主频 + 谱熵（2 维）
    - 通用多频带功率（3 维）
    """
    if not samples:
        raise ValueError("samples must be non-empty")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
    groups, bands = _select_feature_groups(signal_type)

    feats: dict[str, float] = {}
    feats.update(compute_waveform_features(samples))

    if "hrv" in groups:
        feats.update(compute_hrv_features(samples, sample_rate_hz))

    if "spectral" in groups:
        sp = compute_spectral_features(samples, sample_rate_hz)
        feats["dominant_freq"] = sp.get("dominant_freq", 0.0)
        feats["spectral_entropy"] = sp.get("spectral_entropy", 0.0)

    # 通用多频带（所有类型都补一份，便于跨信号比较）
    bp = _band_powers_normalized(samples, sample_rate_hz, bands)
    for k, v in bp.items():
        feats[k] = v

    return feats


def feature_names(signal_type: str = "PPG") -> list[str]:
    """返回指定 signal_type 的特征名（键顺序稳定，供列对齐）。"""
    samples = [0.0] * 128
    sample_rate = 100.0
    if signal_type == "ECG":
        sample_rate = 250.0
    elif signal_type == "EMG":
        sample_rate = 500.0
    elif signal_type == "EEG":
        sample_rate = 250.0
    return list(extract_baseline_features(samples, sample_rate, signal_type).keys())


def to_feature_matrix(sensors: list[Any]) -> tuple[list[float], list[list[float]], list[str]]:
    """把 sensor 列表转为 (labels_hr, X_matrix, feature_names)。

    用于零样本 harness：输入一批 SyntheticSensor，输出训练/评估矩阵。
    """
    if not sensors:
        raise ValueError("sensors must be non-empty")
    first = sensors[0]
    stype = getattr(first, "signal_type")
    sample_rate = getattr(first, "sample_rate_hz")
    names = feature_names(stype)
    X: list[list[float]] = []
    y: list[float] = []
    for s in sensors:
        feats = extract_baseline_features(list(s.samples), s.sample_rate_hz, s.signal_type)
        X.append([float(feats[k]) for k in names])
        y.append(float(getattr(s, "ground_truth_hr_bpm", 0.0)))
    return y, X, names


__all__ = [
    "compute_hrv_features",
    "compute_waveform_features",
    "compute_spectral_features",
    "extract_baseline_features",
    "feature_names",
    "to_feature_matrix",
]
