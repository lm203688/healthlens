"""时序 → 确定性 JSON 序列化引擎（L2 表征层原创点）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。
> 「时序信号的确定性序列化（生态空白）」——「TEMPO / LiPCoT / tsln 均不成熟」。
> 「确定性 → 可审计、可复现、可测试」。

定位：
- **原创点**：把八轴/生理时序信号 → 结构化特征 → JSON 文本的**确定性序列化**方法。
  HealthLens 自创并公开，填补时序 → LLM tokenization 的开源空白。
- 与 L4 XGrammar 强制解码天然衔接：JSON 输出即为受约束解码的 grammar 输入。

内核原则：
- **零第三方依赖**（numpy 已在 dependencies，允许使用；不引入 scipy/sklearn/pandas）。
- 4 阶段管线：Preprocess → Bin → Feature extract → Serialize。
- 输出 hash 幂等：同输入 → 同 JSON 字符串 → 同 sha256。

关键性质（全部有对应测试证明）：
1. 确定性：`serialize(bundle)` 在同输入下必产生同一 JSON 字符串与同一 hash。
2. 幂等：`verify_hash(serialized_json, hash)` 反查校验。
3. 版本化：JSON 顶层固定 `{"schema": "v1", "generator": "healthlens-ts-serializer"}`。
4. Fail-loud：空/单样本/常数序列明确报错或 graceful degradation。
5. Schema 校验器：`validate_serialized(json_str)` 返回 violations 列表。

Wellness 平台术语纪律：仅做统计特征提取与文本化，不做诊断/治疗建议。

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence


# ─────────────────────────── 版本常量 ───────────────────────────

SCHEMA_VERSION = "v1"
GENERATOR_NAME = "healthlens-ts-serializer"

# 顶层字段顺序（用于 JSON 序列化时的字段顺序稳定性）
_TOP_FIELDS_ORDER = (
    "schema",
    "generator",
    "channel_name",
    "unit",
    "sample_rate_hz",
    "subject_hash",
    "session_hash",
    "n_samples",
    "sampling_duration",
    "missing_fraction",
    "bins",
    "features",
)


# ─────────────────────────── 输入模型 ───────────────────────────

@dataclass
class TimeSeriesBundle:
    """时序输入数据封装。

    Attributes:
        channel_name: 通道名（HRV/SpO2/EEG/pulse/HR...），用于选择频带定义
        samples: 等间隔采样数据（list[float]，允许 NaN）
        sample_rate_hz: 采样率（Hz），必须 > 0
        unit: 单位（bpm/ms/umol/μV/%...）
        subject_id: 受试者 id（可选，hash 后用于隐私保护）
        session_id: 会话 id（可选，hash 后用于隐私保护）
    """

    channel_name: str
    samples: list[float]
    sample_rate_hz: float
    unit: str
    subject_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not self.channel_name or not isinstance(self.channel_name, str):
            raise ValueError("channel_name 必须为非空字符串")
        if self.sample_rate_hz is None or self.sample_rate_hz <= 0:
            raise ValueError(f"sample_rate_hz 必须 > 0，收到: {self.sample_rate_hz}")
        if not isinstance(self.samples, (list, tuple)):
            raise ValueError("samples 必须为 list[float]")
        if len(self.samples) == 0:
            raise ValueError("samples 不能为空（fail-loud）")
        # 规范化 samples：允许 NaN，转成 float
        cleaned: list[float] = []
        for i, v in enumerate(self.samples):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                cleaned.append(float("nan"))
            else:
                try:
                    cleaned.append(float(v))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"samples[{i}] 非数值: {v!r}") from exc
        self.samples = cleaned


# ─────────────────────────── 输出模型 ───────────────────────────

@dataclass
class TSSerializedResult:
    """序列化结果。"""

    json_str: str
    structured: dict[str, Any]
    sha256: str
    schema_version: str = SCHEMA_VERSION
    format: Literal["json", "text"] = "json"
    text_lines: list[str] | None = None  # format="text" 时的展开行


# ─────────────────────────── 频带定义 ───────────────────────────

# HRV 经典频带（Berkley 指南）：vLF 0-0.04, LF 0.04-0.15, HF 0.15-0.40, vHF 0.40-Nyquist
_HRV_BANDS = [
    ("vLF", 0.0, 0.04),
    ("LF", 0.04, 0.15),
    ("HF", 0.15, 0.40),
    ("vHF", 0.40, None),  # 到 Nyquist
]

# EEG 经典频带：delta/theta/alpha/beta/gamma
_EEG_BANDS = [
    ("delta", 0.5, 4.0),
    ("theta", 4.0, 8.0),
    ("alpha", 8.0, 13.0),
    ("beta", 13.0, 30.0),
    ("gamma", 30.0, None),
]

# 通用带（默认）
_GENERIC_BANDS = [
    ("low", 0.0, 0.1),
    ("mid", 0.1, 1.0),
    ("high", 1.0, None),
]


def _select_bands(channel_name: str) -> list[tuple[str, float, float | None]]:
    """按通道名选择频带定义。"""
    ch = channel_name.lower()
    if "hrv" in ch:
        return _HRV_BANDS
    if "eeg" in ch:
        return _EEG_BANDS
    return _GENERIC_BANDS


# ─────────────────────────── 隐私 hash ───────────────────────────

def _privacy_hash(value: str) -> str:
    """对 subject_id / session_id 做 sha256 前 16 hex 隐私化。

    目的：JSON 输出中不暴露原始 id，但同一 id 恒定产生同一 hash，
    供外部审计/去重使用。
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────── 阶段 1: Preprocess ───────────────────────────

def _preprocess(samples: list[float]) -> tuple[list[float], list[float], float]:
    """NaN 填充 + 去极值 + 保留原始尺度。

    Args:
        samples: 原始采样数据（可能含 NaN）

    Returns:
        (cleaned_original_scale, zscored, missing_fraction)

    处理逻辑：
        1. NaN 数量统计 → missing_fraction
        2. Forward fill + linear interp：先 forward fill，再 backward fill（首尾兜底）
        3. 3σ 去极值：将超 3σ 的样本替换为最近邻的合法值（保守，不引入新信息）
        4. z-score 归一化：(x - mean) / std；std==0 时返回全 0（graceful）
    """
    n = len(samples)
    if n == 0:
        raise ValueError("空序列")
    n_nan = sum(1 for s in samples if math.isnan(s))
    missing_fraction = n_nan / n

    # 1. NaN → forward fill + backward fill
    cleaned: list[float] = [float("nan")] * n
    last_valid: float | None = None
    for i, v in enumerate(samples):
        if math.isnan(v):
            if last_valid is not None:
                cleaned[i] = last_valid
        else:
            last_valid = v
            cleaned[i] = v
    # backward fill（处理首部 NaN）
    first_valid_idx = None
    for i, v in enumerate(samples):
        if not math.isnan(v):
            first_valid_idx = i
            break
    if first_valid_idx is not None:
        for i in range(first_valid_idx):
            cleaned[i] = samples[first_valid_idx]
    # 若全为 NaN：无法处理，fail-loud
    if first_valid_idx is None:
        raise ValueError("序列全为 NaN，无法序列化（fail-loud）")

    # 2. 去极值：使用 MAD 鲁棒估计替代标准 std，避免极值本身污染 std。
    # 原因：若用 statistics.pstdev，一个巨型极值会把 std 拉大，导致阈值失效。
    # MAD = median(|x - median|)，对正态分布乘以 1.4826 可近似标准差。
    # 特例：MAD=0（大量相同值 + 少量极值）时，任何偏离中位数的样本都视为极值。
    median_val = statistics.median(cleaned)
    mad = statistics.median(abs(v - median_val) for v in cleaned)
    robust_std = mad * 1.4826
    if robust_std > 1e-12:
        threshold = 3.0 * robust_std
        for i in range(n):
            if abs(cleaned[i] - median_val) > threshold:
                cleaned[i] = median_val
    else:
        # MAD=0：中位数本身即稳定值，任何严格偏离都替换为中位数
        for i in range(n):
            if cleaned[i] != median_val:
                cleaned[i] = median_val

    # 3. z-score 归一化（在去极值之后的 cleaned 上计算）
    mean = statistics.fmean(cleaned)
    std = statistics.pstdev(cleaned)
    if std > 1e-12:
        z = [(v - mean) / std for v in cleaned]
    else:
        z = [0.0] * n
    return cleaned, z, missing_fraction


# ─────────────────────────── 阶段 2: Bin ───────────────────────────

def _bin_signals(
    values: list[float],
    sample_rate_hz: float,
    bin_width_s: float,
) -> list[dict[str, float]]:
    """对信号分箱，每 bin 计算 {mean, std, min, max, slope}。

    Args:
        values: 已清理的信号（原始尺度）
        sample_rate_hz: 采样率
        bin_width_s: bin 宽度（秒），默认 1.0

    Returns:
        list of {idx, t_start, t_end, n_samples, mean, std, min, max, slope}
    """
    if bin_width_s <= 0:
        raise ValueError("bin_width_s 必须 > 0")
    n = len(values)
    samples_per_bin = max(1, int(round(bin_width_s * sample_rate_hz)))
    bins: list[dict[str, float]] = []
    for start in range(0, n, samples_per_bin):
        chunk = values[start : start + samples_per_bin]
        if not chunk:
            continue
        m = statistics.fmean(chunk)
        s = statistics.pstdev(chunk) if len(chunk) > 1 else 0.0
        # slope: 线性最小二乘的一阶系数（每秒变化率）
        slope = 0.0
        if len(chunk) >= 2:
            # 简化：端点差分除以时长（等间隔下稳定，避免除法爆炸）
            t_len_s = (len(chunk) - 1) / sample_rate_hz
            if t_len_s > 1e-12:
                slope = (chunk[-1] - chunk[0]) / t_len_s
        idx = start // samples_per_bin
        bins.append({
            "idx": idx,
            "t_start": round(start / sample_rate_hz, 6),
            "t_end": round((start + len(chunk)) / sample_rate_hz, 6),
            "n_samples": len(chunk),
            "mean": round(m, 6),
            "std": round(s, 6),
            "min": round(min(chunk), 6),
            "max": round(max(chunk), 6),
            "slope": round(slope, 6),
        })
    return bins


# ─────────────────────────── 阶段 3a: Time domain ───────────────────────────

def _time_domain_features(values: list[float]) -> dict[str, float]:
    """时域特征：mean, std, cv, skew, kurtosis, rms, mad。"""
    n = len(values)
    if n == 0:
        raise ValueError("空序列")
    m = statistics.fmean(values)
    s = statistics.pstdev(values) if n > 1 else 0.0
    cv = (s / m) if abs(m) > 1e-12 else 0.0
    rms = math.sqrt(statistics.fmean(v * v for v in values))
    # mean absolute deviation
    mad = statistics.fmean(abs(v - m) for v in values)
    if n >= 3 and s > 1e-12:
        # 三阶中心矩
        m3 = statistics.fmean((v - m) ** 3 for v in values)
        m4 = statistics.fmean((v - m) ** 4 for v in values)
        skew = m3 / (s ** 3)
        # 使用 Fisher-Pearson：kurtosis = m4/s^4 - 3（超额峰度）
        kurtosis = (m4 / (s ** 4)) - 3.0
    else:
        skew = 0.0
        kurtosis = 0.0
    return {
        "mean": round(m, 6),
        "std": round(s, 6),
        "cv": round(cv, 6),
        "skew": round(skew, 6),
        "kurtosis": round(kurtosis, 6),
        "rms": round(rms, 6),
        "mad": round(mad, 6),
    }


# ─────────────────────────── 阶段 3b: Frequency domain ───────────────────────────

def _freq_domain_features(
    values: list[float],
    sample_rate_hz: float,
    channel_name: str,
) -> dict[str, Any]:
    """频域特征：dominant_freq, spectral_entropy, band_powers。

    纯 Python 实现 DFT（对长度≤~2000 的序列用 O(n log n) FFT；否则下采样）。
    使用 radix-2 Cooley-Tukey FFT 的纯 Python 版本；对非 2 的幂长度，
    采用零填充至最近的 2 的幂（不改变 dominant 频率，会小幅影响带功率但可接受）。
    """
    n = len(values)
    if n < 4:
        return {
            "dominant_freq": None,
            "spectral_entropy": None,
            "band_powers": {},
        }

    # 去均值（DC 分量移除）
    mean = statistics.fmean(values)
    x = [v - mean for v in values]

    # 选择 FFT 长度：最近的 2 的幂 ≥ n；若 n > 8192，先下采样
    if n > 8192:
        # 均匀下采样到 4096
        step = n / 4096
        x = [x[int(i * step)] for i in range(4096)]
        n = len(x)

    fft_len = 1
    while fft_len < n:
        fft_len <<= 1
    # 零填充
    if fft_len > n:
        x = x + [0.0] * (fft_len - n)

    # 纯 Python FFT（Cooley-Tukey，迭代版）
    spectrum = _fft(x)

    # 单侧功率谱（只取前半）
    half = fft_len // 2
    power = [(spectrum[i][0] ** 2 + spectrum[i][1] ** 2) for i in range(half)]
    # 归一化（总功率 = 1）
    total_power = sum(power)
    if total_power <= 0:
        return {
            "dominant_freq": 0.0,
            "spectral_entropy": 0.0,
            "band_powers": {name: 0.0 for name, _, _ in _select_bands(channel_name)},
        }
    norm_power = [p / total_power for p in power]

    # dominant freq
    if norm_power:
        max_idx = max(range(len(norm_power)), key=lambda i: norm_power[i])
        dominant_freq = max_idx * sample_rate_hz / fft_len
    else:
        dominant_freq = 0.0

    # spectral entropy（Shannon，以 2 为底，归一化到 [0, 1]）
    entropy_bits = 0.0
    for p in norm_power:
        if p > 0:
            entropy_bits -= p * math.log2(p)
    max_entropy = math.log2(half) if half > 1 else 1.0
    spectral_entropy = entropy_bits / max_entropy if max_entropy > 0 else 0.0

    # band_powers：按通道选择频带
    nyquist = sample_rate_hz / 2.0
    bands = _select_bands(channel_name)
    band_powers: dict[str, float] = {}
    band_sum = 0.0
    for name, f_lo, f_hi in bands:
        f_hi_eff = nyquist if f_hi is None else f_hi
        lo_bin = max(0, int(math.floor(f_lo * fft_len / sample_rate_hz)))
        hi_bin = min(half - 1, int(math.ceil(f_hi_eff * fft_len / sample_rate_hz)))
        if hi_bin < lo_bin:
            band_powers[name] = 0.0
            continue
        bp = sum(norm_power[lo_bin : hi_bin + 1])
        band_powers[name] = bp
        band_sum += bp
    # 归一化 band_powers 求和 = 1（±1e-9）
    if band_sum > 1e-12:
        band_powers = {k: v / band_sum for k, v in band_powers.items()}

    return {
        "dominant_freq": round(dominant_freq, 6),
        "spectral_entropy": round(spectral_entropy, 6),
        "band_powers": {k: round(v, 9) for k, v in band_powers.items()},
    }


def _fft(values: list[float]) -> list[tuple[float, float]]:
    """纯 Python radix-2 Cooley-Tukey FFT（长度必须为 2 的幂）。

    Returns:
        长度为 N 的复数序列 [(re, im), ...]
    """
    n = len(values)
    if n == 0:
        return []
    if n & (n - 1) != 0:
        raise ValueError("FFT 输入长度必须为 2 的幂")
    if n == 1:
        return [(values[0], 0.0)]

    # 位逆序重排
    bits = n.bit_length() - 1
    result = [0.0 + 0.0j] * n
    for i in range(n):
        # bit reverse
        rev = 0
        x = i
        for _ in range(bits):
            rev = (rev << 1) | (x & 1)
            x >>= 1
        result[rev] = values[i] + 0.0j

    # 迭代 FFT
    size = 2
    while size <= n:
        half = size // 2
        # twiddle factor
        twiddle_angle = -2.0 * math.pi / size
        for start in range(0, n, size):
            for k in range(half):
                angle = twiddle_angle * k
                twiddle = (
                    math.cos(angle) + 1j * math.sin(angle)
                )
                even = result[start + k]
                odd = result[start + k + half] * twiddle
                result[start + k] = even + odd
                result[start + k + half] = even - odd
        size *= 2

    return [(c.real, c.imag) for c in result]


# ─────────────────────────── 阶段 3c: Shape features ───────────────────────────

def _shape_features(values: list[float], sample_rate_hz: float) -> dict[str, float]:
    """形状特征：hurst_exponent, fractal_dimension, approximate_entropy。"""
    n = len(values)
    if n < 8:
        return {
            "hurst_exponent": None,
            "fractal_dimension": None,
            "approximate_entropy": None,
        }
    h = _hurst_dfa(values)
    fd = _fractal_dimension(values, sample_rate_hz)
    ae = _approximate_entropy(values)
    return {
        "hurst_exponent": round(h, 6) if h is not None else None,
        "fractal_dimension": round(fd, 6) if fd is not None else None,
        "approximate_entropy": round(ae, 6) if ae is not None else None,
    }


def _hurst_dfa(values: list[float]) -> float | None:
    """Hurst 指数（DFA 简版）。

    算法（Peng et al. 1994）：
    1. 累计和剖面 Y(k) = sum_{i=1..k}(x_i - <x>)
    2. 对多个尺度 n（如 16, 32, 64, ...），把 Y 切成 L 段
    3. 每段做线性最小二乘去趋势，计算残差方差 F^2(n)
    4. log F(n) ~ H * log n + c，回归斜率即 H

    H ≈ 0.5 → 白噪声（无自相关）
    H > 0.5 → 长程正相关（趋势性）
    H < 0.5 → 反相关（振荡）
    """
    n = len(values)
    if n < 32:
        return None

    mean = statistics.fmean(values)
    y = [0.0]
    acc = 0.0
    for v in values:
        acc += v - mean
        y.append(acc)

    # 选择尺度
    scales: list[int] = []
    s = 16
    while s * 2 <= n:
        scales.append(s)
        s *= 2
    if len(scales) < 3:
        return None

    log_scales: list[float] = []
    log_Fs: list[float] = []

    for scale in scales:
        variances: list[float] = []
        for start in range(0, n, scale):
            end = min(start + scale, n)
            if end - start < scale:
                break
            segment_y = y[start : end + 1]
            # 线性最小二乘拟合 y = a*t + b
            ts = list(range(len(segment_y)))
            tm = statistics.fmean(ts)
            ym = statistics.fmean(segment_y)
            var_t = sum((t - tm) ** 2 for t in ts)
            if var_t == 0:
                continue
            cov = sum((ts[i] - tm) * (segment_y[i] - ym) for i in range(len(ts)))
            a = cov / var_t
            b = ym - a * tm
            var = statistics.pstdev([segment_y[i] - (a * ts[i] + b) for i in range(len(ts))]) ** 2
            variances.append(var)
        if not variances:
            continue
        F2 = statistics.fmean(variances)
        if F2 > 0:
            log_scales.append(math.log(scale))
            log_Fs.append(math.log(math.sqrt(F2)))

    if len(log_scales) < 3:
        return None
    # 线性回归
    m = statistics.fmean(log_scales)
    mm = statistics.fmean(log_Fs)
    num = sum((log_scales[i] - m) * (log_Fs[i] - mm) for i in range(len(log_scales)))
    den = sum((log_scales[i] - m) ** 2 for i in range(len(log_scales)))
    if den == 0:
        return None
    h = num / den
    # 数值稳定：截断到 [0, 1]
    if h < 0:
        return 0.0
    if h > 1:
        return 1.0
    return h


def _fractal_dimension(values: list[float], sample_rate_hz: float) -> float | None:
    """分形维数（box-counting，1D 曲线用样本点密度近似）。

    实现：以不同步长 s 遍历曲线，统计"新格子"覆盖数 N(s)，
    拟合 log N ~ -D * log s + c，回归斜率的负值即 D。

    对平滑曲线 D ≈ 1，对分形曲线 D 略大于 1（如 1D 布朗运动 ≈ 1.5）。
    """
    n = len(values)
    if n < 16:
        return None

    # 归一化 y 到 [0, 1]
    vmin = min(values)
    vmax = max(values)
    if vmax - vmin < 1e-12:
        return 1.0

    log_s: list[float] = []
    log_N: list[float] = []
    s = 1
    while s * 2 <= n:
        if s * 2 > n:
            break
        # 统计不同 (floor(x/s), floor((y-vmin)/(vmax-vmin)*s)) 唯一组合数
        cells: set[tuple[int, int]] = set()
        span = vmax - vmin
        for x_idx, v in enumerate(values):
            cy = int((v - vmin) / span * s) if span > 0 else 0
            cx = x_idx // max(1, n // s) if n // s > 0 else 0
            cells.add((cx, cy))
        log_s.append(math.log(s))
        log_N.append(math.log(len(cells)))
        s *= 2

    if len(log_s) < 3:
        return None
    m = statistics.fmean(log_s)
    mm = statistics.fmean(log_N)
    num = sum((log_s[i] - m) * (log_N[i] - mm) for i in range(len(log_s)))
    den = sum((log_s[i] - m) ** 2 for i in range(len(log_s)))
    if den == 0:
        return None
    D = -num / den
    # 截断到 [1, 2]
    if D < 1.0:
        return 1.0
    if D > 2.0:
        return 2.0
    return D


def _approximate_entropy(values: list[float], m: int = 2, r_ratio: float = 0.2) -> float | None:
    """近似熵（Pincus 1991）。

    算法：
    1. r = r_ratio * std(values)
    2. 对相位空间重构 φ_i = (x_i, x_{i+1}, ..., x_{i+m-1})
    3. 计算 A(m) = |{j≠i: max_k|φ_i[k]-φ_j[k]| < r}| / (N-m+1) 的平均
    4. AE = log(A(m)/A(m+1))

    注意：为数值稳定，排除自匹配（j ≠ i），并对常数序列返回 0。
    """
    n = len(values)
    if n < 2 * m + 1:
        return None
    if n > 500:
        # 均匀下采样到 250，防止 O(n^2) 爆炸
        step = n / 250
        values = [values[int(i * step)] for i in range(250)]
        n = len(values)

    s = statistics.pstdev(values) if len(values) > 1 else 0.0
    if s < 1e-12:
        return 0.0
    r = r_ratio * s

    def phi(mm: int) -> float:
        N = n - mm + 1
        if N <= 0:
            return 0.0
        total = 0
        for i in range(N):
            for j in range(N):
                if i == j:
                    continue
                max_diff = 0.0
                for k in range(mm):
                    d = abs(values[i + k] - values[j + k])
                    if d > max_diff:
                        max_diff = d
                        if max_diff >= r:
                            break
                if max_diff < r:
                    total += 1
        return total / (N * (N - 1)) if N > 1 else 0.0

    a_m = phi(m)
    a_m1 = phi(m + 1)
    if a_m <= 0 or a_m1 <= 0:
        return 0.0
    return math.log(a_m / a_m1)


# ─────────────────────────── 阶段 3d: Context features ───────────────────────────

def _context_features(
    original_samples: list[float],
    cleaned: list[float],
    sample_rate_hz: float,
    missing_fraction: float,
) -> dict[str, float]:
    """上下文特征：sampling_duration, sample_count, missing_fraction, monotonic_fraction。"""
    n = len(original_samples)
    duration = n / sample_rate_hz if sample_rate_hz > 0 else 0.0

    # 单调比例：相邻差分同号比例
    diffs: list[float] = []
    for i in range(1, n):
        if math.isnan(original_samples[i]) or math.isnan(original_samples[i - 1]):
            continue
        diffs.append(original_samples[i] - original_samples[i - 1])
    if len(diffs) < 2:
        monotonic_fraction = 0.0
    else:
        signs = [(1 if d > 0 else (-1 if d < 0 else 0)) for d in diffs]
        # 连续同号的比例
        same = 0
        for i in range(1, len(signs)):
            if signs[i] == signs[i - 1] and signs[i] != 0:
                same += 1
        monotonic_fraction = same / (len(signs) - 1) if len(signs) > 1 else 0.0

    return {
        "sampling_duration": round(duration, 6),
        "sample_count": n,
        "missing_fraction": round(missing_fraction, 6),
        "monotonic_fraction": round(monotonic_fraction, 6),
    }


# ─────────────────────────── 阶段 4: Serialize ───────────────────────────

def _round_float(v: float, digits: int = 6) -> float:
    """稳定四舍五入（避免 -0.0）。"""
    r = round(v, digits)
    if r == 0:
        r = 0.0
    return r


def _to_json_str(structured: dict[str, Any]) -> str:
    """确定性 JSON 序列化：sort_keys + compact separators。"""
    return json.dumps(
        structured,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expand_to_text(structured: dict[str, Any]) -> list[str]:
    """JSON 展开成 LLM 可读的行式文本。"""
    lines: list[str] = []
    lines.append(f"# {GENERATOR_NAME} schema={SCHEMA_VERSION}")
    for k in _TOP_FIELDS_ORDER:
        if k not in structured:
            continue
        v = structured[k]
        if isinstance(v, dict):
            lines.append(f"[{k}]")
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    lines.append(f"  {kk}:")
                    for kkk, vvv in vv.items():
                        lines.append(f"    {kkk}={vvv}")
                elif isinstance(vv, list):
                    lines.append(f"  {kk}={vv}")
                else:
                    lines.append(f"  {kk}={vv}")
        elif isinstance(v, list):
            # bins 顶层字段：展开成每 bin 一行
            if k == "bins":
                lines.append(f"bins (n={len(v)}):")
                for b in v:
                    if isinstance(b, dict):
                        lines.append(
                            f"  bin[{b.get('idx')}] t={b.get('t_start')}-{b.get('t_end')}s "
                            f"n={b.get('n_samples')} mean={b.get('mean')} "
                            f"std={b.get('std')} min={b.get('min')} max={b.get('max')} "
                            f"slope={b.get('slope')}"
                        )
                    else:
                        lines.append(f"  bin={b}")
            else:
                lines.append(f"{k}=[{len(v)} items]")
        else:
            lines.append(f"{k}={v}")
    return lines


# ─────────────────────────── 主入口 ───────────────────────────

@dataclass
class SerializeOptions:
    """序列化可配置项。"""

    bin_width_s: float = 1.0
    apply_zscore: bool = False  # 是否在 JSON 里保留 z-scored 序列（默认只保留原始尺度）
    enable_time_domain: bool = True
    enable_freq_domain: bool = True
    enable_shape: bool = True
    enable_context: bool = True
    include_bins: bool = True
    max_bins: int = 3600  # 输出 bin 数上限，防止 JSON 过大


def serialize(
    bundle: TimeSeriesBundle,
    options: SerializeOptions | None = None,
    format: Literal["json", "text"] = "json",
) -> TSSerializedResult:
    """把 TimeSeriesBundle 序列化为确定性 JSON。

    Args:
        bundle: 输入时序
        options: 可选参数（bin 宽度、特征组开关）
        format: "json" 或 "text"

    Returns:
        TSSerializedResult(json_str, structured, sha256, schema_version, format, text_lines)
    """
    if options is None:
        options = SerializeOptions()

    samples = bundle.samples
    n = len(samples)

    # Graceful degradation：单样本返回极简结构
    if n == 1:
        v = samples[0]
        if math.isnan(v):
            raise ValueError("单样本且为 NaN，无法序列化（fail-loud）")
        structured_single = {
            "schema": SCHEMA_VERSION,
            "generator": GENERATOR_NAME,
            "channel_name": bundle.channel_name,
            "unit": bundle.unit,
            "sample_rate_hz": bundle.sample_rate_hz,
            "subject_hash": _privacy_hash(bundle.subject_id) if bundle.subject_id else None,
            "session_hash": _privacy_hash(bundle.session_id) if bundle.session_id else None,
            "n_samples": 1,
            "sampling_duration": round(1.0 / bundle.sample_rate_hz, 6),
            "missing_fraction": 0.0,
            "bins": [{"idx": 0, "t_start": 0.0, "t_end": round(1.0 / bundle.sample_rate_hz, 6), "n_samples": 1, "mean": round(v, 6), "std": 0.0, "min": round(v, 6), "max": round(v, 6), "slope": 0.0}],
            "features": {
                "time_domain": {"mean": round(v, 6), "std": 0.0, "cv": 0.0, "skew": 0.0, "kurtosis": 0.0, "rms": round(abs(v), 6), "mad": 0.0},
                "freq_domain": {"dominant_freq": None, "spectral_entropy": None, "band_powers": {}},
                "shape": {"hurst_exponent": None, "fractal_dimension": None, "approximate_entropy": None},
                "context": {"sampling_duration": round(1.0 / bundle.sample_rate_hz, 6), "sample_count": 1, "missing_fraction": 0.0, "monotonic_fraction": 0.0},
            },
        }
        json_str = _to_json_str(structured_single)
        sha = _compute_sha256(json_str)
        return TSSerializedResult(
            json_str=json_str,
            structured=structured_single,
            sha256=sha,
            schema_version=SCHEMA_VERSION,
            format=format,
            text_lines=_expand_to_text(structured_single) if format == "text" else None,
        )

    # ── 4 阶段管线 ──
    cleaned, zscored, missing_fraction = _preprocess(samples)

    # 常数序列 graceful degradation：保留 time_domain + context
    is_constant = all(cleaned[i] == cleaned[0] for i in range(len(cleaned)))

    # Bin
    if options.include_bins:
        bins = _bin_signals(cleaned, bundle.sample_rate_hz, options.bin_width_s)
        if len(bins) > options.max_bins:
            bins = bins[: options.max_bins]
    else:
        bins = []

    # Features
    features: dict[str, Any] = {}
    if options.enable_time_domain:
        features["time_domain"] = _time_domain_features(cleaned)
    if options.enable_freq_domain:
        features["freq_domain"] = _freq_domain_features(cleaned, bundle.sample_rate_hz, bundle.channel_name)
    if options.enable_shape and not is_constant:
        features["shape"] = _shape_features(cleaned, bundle.sample_rate_hz)
    elif options.enable_shape and is_constant:
        features["shape"] = {"hurst_exponent": None, "fractal_dimension": None, "approximate_entropy": 0.0}
    if options.enable_context:
        features["context"] = _context_features(samples, cleaned, bundle.sample_rate_hz, missing_fraction)

    # 组装
    structured: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "generator": GENERATOR_NAME,
        "channel_name": bundle.channel_name,
        "unit": bundle.unit,
        "sample_rate_hz": bundle.sample_rate_hz,
        "subject_hash": _privacy_hash(bundle.subject_id) if bundle.subject_id else None,
        "session_hash": _privacy_hash(bundle.session_id) if bundle.session_id else None,
        "n_samples": n,
        "sampling_duration": round(n / bundle.sample_rate_hz, 6),
        "missing_fraction": round(missing_fraction, 6),
        "bins": bins,
        "features": features,
    }

    json_str = _to_json_str(structured)
    sha = _compute_sha256(json_str)

    return TSSerializedResult(
        json_str=json_str,
        structured=structured,
        sha256=sha,
        schema_version=SCHEMA_VERSION,
        format=format,
        text_lines=_expand_to_text(structured) if format == "text" else None,
    )


# ─────────────────────────── 校验与验证 ───────────────────────────

def verify_hash(serialized_json: str, expected_sha256: str) -> bool:
    """幂等反查：给定 JSON 字符串与期望 hash，判断是否匹配。"""
    return _compute_sha256(serialized_json) == expected_sha256


def compute_hash(serialized_json: str) -> str:
    """计算 JSON 字符串的 sha256。"""
    return _compute_sha256(serialized_json)


def validate_serialized(json_str: str) -> list[str]:
    """Schema 校验器：返回 violations 列表。

    检查：
    - JSON 可解析
    - 顶层 schema / generator 字段存在且值正确
    - 必要字段完整（channel_name, unit, sample_rate_hz, n_samples, features）
    - n_samples ≥ 1
    - band_powers 求和 ≈ 1（±1e-6）
    - 未知字段（顶层多出字段）仅告警不拒绝

    Returns:
        violations: 空列表表示通过；否则每条为 "[severity] [field]: [message]"
    """
    violations: list[str] = []

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as exc:
        return [f"[error] json: invalid JSON ({exc.msg})"]

    if not isinstance(parsed, dict):
        return [f"[error] root: expected object, got {type(parsed).__name__}"]

    # 必需字段检查
    required_top = ["schema", "generator", "channel_name", "unit", "sample_rate_hz", "n_samples", "features"]
    for k in required_top:
        if k not in parsed:
            violations.append(f"[error] {k}: missing required field")

    # schema 版本
    if parsed.get("schema") != SCHEMA_VERSION:
        violations.append(f"[error] schema: expected '{SCHEMA_VERSION}', got '{parsed.get('schema')}'")
    if parsed.get("generator") != GENERATOR_NAME:
        violations.append(f"[error] generator: expected '{GENERATOR_NAME}', got '{parsed.get('generator')}'")

    # 类型检查
    if "sample_rate_hz" in parsed:
        v = parsed["sample_rate_hz"]
        if not isinstance(v, (int, float)) or v <= 0:
            violations.append(f"[error] sample_rate_hz: must be positive number, got {v!r}")
    if "n_samples" in parsed:
        v = parsed["n_samples"]
        if not isinstance(v, int) or v < 1:
            violations.append(f"[error] n_samples: must be int >= 1, got {v!r}")
    if "channel_name" in parsed and not isinstance(parsed["channel_name"], str):
        violations.append(f"[error] channel_name: must be string")

    # features 校验
    features = parsed.get("features", {})
    if not isinstance(features, dict):
        violations.append(f"[error] features: expected object, got {type(features).__name__}")
    else:
        # band_powers 求和 ≈ 1
        freq = features.get("freq_domain", {})
        if isinstance(freq, dict):
            bp = freq.get("band_powers", {})
            if isinstance(bp, dict) and bp:
                total = sum(v for v in bp.values() if isinstance(v, (int, float)))
                if abs(total - 1.0) > 1e-6:
                    violations.append(
                        f"[error] features.freq_domain.band_powers: sum={total:.9f}, expected 1.0 (±1e-6)"
                    )

    # bins 校验
    bins = parsed.get("bins", [])
    if isinstance(bins, list):
        for i, b in enumerate(bins):
            if not isinstance(b, dict):
                violations.append(f"[error] bins[{i}]: expected object")
                continue
            for k in ("idx", "mean", "std", "min", "max"):
                if k not in b:
                    violations.append(f"[error] bins[{i}].{k}: missing")
    else:
        violations.append(f"[error] bins: expected list, got {type(bins).__name__}")

    # 未知字段告警（不阻断）
    known_top = set(_TOP_FIELDS_ORDER) | {"schema_version", "generator_version"}
    for k in parsed.keys():
        if k not in known_top:
            violations.append(f"[warn] {k}: unknown top-level field")

    return violations


__all__ = [
    "SCHEMA_VERSION",
    "GENERATOR_NAME",
    "TimeSeriesBundle",
    "TSSerializedResult",
    "SerializeOptions",
    "serialize",
    "verify_hash",
    "compute_hash",
    "validate_serialized",
    "_preprocess",
    "_bin_signals",
    "_time_domain_features",
    "_freq_domain_features",
    "_shape_features",
    "_context_features",
    "_hurst_dfa",
    "_fractal_dimension",
    "_approximate_entropy",
    "_fft",
    "_privacy_hash",
]
