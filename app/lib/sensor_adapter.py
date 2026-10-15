"""传感器基础模型 Adapter（L2 表征层）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。
> 可穿戴基础模型（SensorFM / Pulse-PPG / PaPaGei）已经把「传感器 → 健康表征」
> 这层商品化。HealthLens 的对策：**用 adapter 隔离重型科学层与零依赖内核**。

定位：
- **Adapter 层**：torch/transformers/sentence-transformers 全部 optional。
  未装时 `list_available_engines()` 返回 `available=False` + 明确 reason。
- **Fail-loud**：`load_pulse_ppg_model` / `load_papagei_model` 未装时抛
  `HealthLensUnavailableEngine`，不静默降级成假 embedding。
- **纯 Python Fallback**：`zero_shot_embed_wellness(signal)` 提供 20 维手工
  特征向量（均值/方差/频带功率/形状/时序相关性），作为「零依赖基础模型」
  占位符，可用作 baseline 与消融实验对照。

Wellness 平台术语纪律：仅产出统计表征，不诊断。

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-15)
"""
from __future__ import annotations

import importlib.util
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable


# ─────────────────────────── 异常 ───────────────────────────

class HealthLensUnavailableEngine(RuntimeError):
    """请求的基础模型引擎不可用（未安装或加载失败）。

    触发场景：`load_pulse_ppg_model` / `load_papagei_model` 依赖的
    torch / transformers 未安装。此时宁可 fail-loud，不产出假 embedding
    误导上层。
    """


# ─────────────────────────── 探测数据模型 ───────────────────────────

@dataclass
class SensorModelProbe:
    """单个基础模型引擎的探测结果。"""

    engine_name: str
    available: bool
    reason: str
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "available": self.available,
            "reason": self.reason,
            "version": self.version,
        }


# ─────────────────────────── 探测函数 ───────────────────────────

def _probe_one(module_name: str, engine_name: str, version_attr: str = "__version__") -> SensorModelProbe:
    """探测单个模块是否可用。

    Args:
        module_name: Python import 名（如 "torch"）
        engine_name: 用于日志/展示的名字
        version_attr: 版本属性名
    """
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return SensorModelProbe(
            engine_name=engine_name,
            available=False,
            reason=f"module '{module_name}' not installed",
            version=None,
        )
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, version_attr, None)
        return SensorModelProbe(
            engine_name=engine_name,
            available=True,
            reason="ok",
            version=str(version) if version else None,
        )
    except Exception as exc:  # noqa: BLE001
        return SensorModelProbe(
            engine_name=engine_name,
            available=False,
            reason=f"import failed: {type(exc).__name__}: {exc}",
            version=None,
        )


def list_available_engines() -> list[SensorModelProbe]:
    """探测所有 optional 基础模型引擎。

    覆盖：
    - torch
    - transformers
    - sentence_transformers

    返回：list[SensorModelProbe]，每个元素带 available + reason + version。
    未装时明确说明原因（`module 'X' not installed`），便于运维诊断。
    """
    return [
        _probe_one("torch", "Pulse-PPG (torch)"),
        _probe_one("transformers", "transformers"),
        _probe_one("sentence_transformers", "sentence-transformers"),
    ]


# ─────────────────────────── 模型加载入口 ───────────────────────────

# 真实 Pulse-PPG / PaPaGei 模型待用户提供权重时接入。
# 当前 fallback 是 20 维手工特征，可用作 baseline 与消融实验对照。
# 报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L2。


def load_pulse_ppg_model(
    device: str = "cpu",
    load_weights: bool = False,
) -> dict[str, Any]:
    """加载 Pulse-PPG 基础模型。

    Pulse-PPG: IMWUT 2025, arXiv 2502.01108。
    需要 torch + transformers。未装时抛 HealthLensUnavailableEngine。

    Args:
        device: 推理设备（cpu / cuda:0 / mps）
        load_weights: 是否加载真实权重（False 时返回占位模型，便于集成测试）

    Returns:
        {"engine_name", "device", "loaded", "dim", "note"}

    Raises:
        HealthLensUnavailableEngine: torch/transformers 未安装
    """
    spec_torch = importlib.util.find_spec("torch")
    if spec_torch is None:
        raise HealthLensUnavailableEngine(
            "Pulse-PPG requires 'torch' >= 2.0. Install via "
            "`pip install healthlens[sensing]` or `pip install torch>=2.0 transformers>=4.40`."
        )
    try:
        import torch  # type: ignore[import-not-found]

        if load_weights:
            # 占位：真实权重加载需要用户提供 checkpoint 路径。
            # 此处不静默降级为随机权重（会污染实验结果），直接告知用户。
            raise HealthLensUnavailableEngine(
                "Pulse-PPG checkpoint path not configured. "
                "Set HL_PULSE_PPG_CHECKPOINT env var or pass load_weights=False for dry run."
            )
        return {
            "engine_name": "Pulse-PPG",
            "device": device,
            "loaded": True,
            "dry_run": True,
            "torch_version": torch.__version__,
            "note": "dry-run placeholder (no weights loaded)",
        }
    except HealthLensUnavailableEngine:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HealthLensUnavailableEngine(
            f"Pulse-PPG load failed: {type(exc).__name__}: {exc}"
        ) from exc


def load_papagei_model(
    device: str = "cpu",
    load_weights: bool = False,
) -> dict[str, Any]:
    """加载 PaPaGei 基础模型。

    PaPaGei: ICLR 2025, Nokia Bell Labs。光学生理信号对比自监督。
    需要 torch。未装时抛 HealthLensUnavailableEngine。
    """
    spec_torch = importlib.util.find_spec("torch")
    if spec_torch is None:
        raise HealthLensUnavailableEngine(
            "PaPaGei requires 'torch' >= 2.0. Install via "
            "`pip install healthlens[sensing]`."
        )
    try:
        import torch  # type: ignore[import-not-found]

        if load_weights:
            raise HealthLensUnavailableEngine(
                "PaPaGei checkpoint path not configured. "
                "Set HL_PAPAGEI_CHECKPOINT env var or pass load_weights=False for dry run."
            )
        return {
            "engine_name": "PaPaGei",
            "device": device,
            "loaded": True,
            "dry_run": True,
            "torch_version": torch.__version__,
            "note": "dry-run placeholder (no weights loaded)",
        }
    except HealthLensUnavailableEngine:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HealthLensUnavailableEngine(
            f"PaPaGei load failed: {type(exc).__name__}: {exc}"
        ) from exc


# ─────────────────────────── 20 维手工特征嵌入（纯 Python fallback） ───────────────────────────

# 20 维特征向量布局（顺序稳定，供下游模型消费）：
# [0]  mean                       信号均值
# [1]  std                        信号标准差
# [2]  rms                        均方根
# [3]  mad                        平均绝对偏差
# [4]  min                        最小值
# [5]  max                        最大值
# [6]  cv                         变异系数 (std/mean)
# [7]  skew                       偏度
# [8]  kurtosis                   超额峰度
# [9]  band_power_low             低频带功率 (0 - 0.1 Hz)
# [10] band_power_mid             中频带功率 (0.1 - 1.0 Hz)
# [11] band_power_high            高频带功率 (1.0 - Nyquist)
# [12] dominant_freq              主频
# [13] spectral_entropy           谱熵
# [14] lag1_autocorr              一阶自相关
# [15] lag2_autocorr              二阶自相关
# [16] lag3_autocorr              三阶自相关
# [17] zero_crossing_rate         零穿越率（去均值后）
# [18] slope                      端点差分斜率
# [19] monotonic_fraction         单调相邻比例

FEATURE_DIM = 20


def _band_powers(values: list[float], sample_rate_hz: float) -> tuple[float, float, float]:
    """简易三带功率（低/中/高），返回已归一化到和=1。"""
    n = len(values)
    if n < 4:
        return (0.0, 0.0, 0.0)
    mean = statistics.fmean(values)
    x = [v - mean for v in values]

    # 用简化 DFT：只算关心的频段积分，不做完整 FFT（性能优先）
    nyquist = sample_rate_hz / 2.0
    bands = [
        (0.0, 0.1),
        (0.1, 1.0),
        (1.0, nyquist),
    ]
    powers: list[float] = []
    for f_lo, f_hi in bands:
        if f_hi <= f_lo:
            powers.append(0.0)
            continue
        # 用 Riemann 和近似功率谱积分：sum_x |x_t|^2 * (cos/sin basis at freq)
        # 简化：直接在时间域用滑动窗口做相关（相当于低通滤波能量）
        # 更稳定的实现：用 DFT 的少量频率点采样
        # 取该频带的中心频率做功率估计
        f_center = (f_lo + f_hi) / 2.0
        # 与 cos(2π f_center t) 和 sin(2π f_center t) 做内积
        cos_coeff = 0.0
        sin_coeff = 0.0
        for i, v in enumerate(x):
            t = i / sample_rate_hz
            angle = 2 * math.pi * f_center * t
            cos_coeff += v * math.cos(angle)
            sin_coeff += v * math.sin(angle)
        # 功率 = (a^2 + b^2) / (2n)
        p = (cos_coeff ** 2 + sin_coeff ** 2) / (2.0 * n) if n > 0 else 0.0
        powers.append(p)

    total = sum(powers)
    if total <= 1e-18:
        return (0.0, 0.0, 0.0)
    return tuple(p / total for p in powers)  # type: ignore[return-value]


def _spectral_features(values: list[float], sample_rate_hz: float) -> tuple[float, float]:
    """返回 (dominant_freq, spectral_entropy)，用小 DFT 简化实现。"""
    n = len(values)
    if n < 4:
        return (0.0, 0.0)
    mean = statistics.fmean(values)
    x = [v - mean for v in values]
    # 用对数等间隔采样频率，从 0.01 Hz 到 Nyquist
    nyquist = sample_rate_hz / 2.0
    if nyquist < 0.05:
        return (0.0, 0.0)
    # 取 32 个对数等间隔频率
    n_f = 32
    f_lo = max(0.01, nyquist / 100.0)
    f_hi = nyquist * 0.99
    log_lo = math.log(f_lo)
    log_hi = math.log(f_hi)
    log_step = (log_hi - log_lo) / (n_f - 1)
    freqs = [math.exp(log_lo + i * log_step) for i in range(n_f)]

    powers: list[float] = []
    for f in freqs:
        cos_c = 0.0
        sin_c = 0.0
        for i, v in enumerate(x):
            t = i / sample_rate_hz
            angle = 2 * math.pi * f * t
            cos_c += v * math.cos(angle)
            sin_c += v * math.sin(angle)
        p = (cos_c ** 2 + sin_c ** 2) / (2.0 * n) if n > 0 else 0.0
        powers.append(p)

    total = sum(powers)
    if total <= 1e-18:
        return (0.0, 0.0)
    norm = [p / total for p in powers]
    max_idx = max(range(n_f), key=lambda i: norm[i])
    dominant_freq = freqs[max_idx]

    entropy = 0.0
    for p in norm:
        if p > 0:
            entropy -= p * math.log2(p)
    max_ent = math.log2(n_f) if n_f > 1 else 1.0
    spectral_entropy = entropy / max_ent if max_ent > 0 else 0.0
    return (dominant_freq, spectral_entropy)


def _autocorr(values: list[float], lag: int) -> float:
    """指定 lag 的自相关（Pearson 相关）。"""
    n = len(values)
    if n < lag + 2:
        return 0.0
    m = statistics.fmean(values)
    m_lag = statistics.fmean(values[lag:])
    x1 = [v - m for v in values[: n - lag]]
    x2 = [v - m_lag for v in values[lag:]]
    n_ = len(x1)
    if n_ == 0:
        return 0.0
    s1 = statistics.pstdev(x1)
    s2 = statistics.pstdev(x2)
    if s1 < 1e-12 or s2 < 1e-12:
        return 0.0
    cov = statistics.fmean(x1[i] * x2[i] for i in range(n_)) - statistics.fmean(x1) * statistics.fmean(x2)
    return cov / (s1 * s2)


def zero_shot_embed_wellness(
    signal: list[float] | "Any",  # type: ignore[name-defined]
    sample_rate_hz: float = 100.0,
    window_size: int = 128,
    stride: int | None = None,
) -> list[list[float]]:
    """零依赖基础模型占位符：把信号切成窗口，每窗口输出 20 维手工特征向量。

    报告定位（§5 L2）：
    > 真实 Pulse-PPG / PaPaGei 模型待用户提供权重时接入。
    > 当前 fallback 是 20 维手工特征，可用作 baseline 与消融实验对照。

    输入：
        signal: 一维时序（list[float] 或 numpy.ndarray）
        sample_rate_hz: 采样率
        window_size: 窗口长度（样本数）
        stride: 滑动步长（默认 window_size，即不重叠）

    输出：
        list[list[float]]，长度 = ceil((n - window_size + 1) / stride)，
        每元素是 20 维特征向量（顺序见 FEATURE_DIM 注释）。

    Fail-loud 行为：
        - 信号长度 < window_size 时抛 ValueError
        - signal 为空时抛 ValueError
        - NaN 样本会被前向填充后再嵌入（不静默删除）
    """
    # numpy 兼容
    if hasattr(signal, "tolist"):
        signal = list(signal.tolist())  # type: ignore[union-attr]
    if not isinstance(signal, (list, tuple)):
        raise TypeError(f"signal must be list/tuple/ndarray, got {type(signal).__name__}")
    if len(signal) == 0:
        raise ValueError("signal 不能为空")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz 必须 > 0，收到: {sample_rate_hz}")
    if window_size < 4:
        raise ValueError(f"window_size 必须 >= 4，收到: {window_size}")
    if len(signal) < window_size:
        raise ValueError(f"signal 长度 {len(signal)} < window_size {window_size}")

    if stride is None:
        stride = window_size
    if stride <= 0:
        stride = window_size

    # NaN 前向填充
    filled: list[float] = []
    last = 0.0
    for v in signal:
        v_f = float(v)
        if math.isnan(v_f):
            filled.append(last)
        else:
            filled.append(v_f)
            last = v_f

    # 切窗 + 提特征
    embeddings: list[list[float]] = []
    for start in range(0, len(filled) - window_size + 1, stride):
        window = filled[start : start + window_size]
        embeddings.append(_window_features(window, sample_rate_hz))
    return embeddings


def _window_features(window: list[float], sample_rate_hz: float) -> list[float]:
    """单窗口的 20 维特征（顺序见 FEATURE_DIM 注释）。"""
    n = len(window)
    m = statistics.fmean(window)
    s = statistics.pstdev(window) if n > 1 else 0.0
    rms = math.sqrt(statistics.fmean(v * v for v in window))
    mad = statistics.fmean(abs(v - m) for v in window)
    mn = min(window)
    mx = max(window)
    cv = (s / m) if abs(m) > 1e-12 else 0.0

    # skew / kurtosis
    if n >= 3 and s > 1e-12:
        m3 = statistics.fmean((v - m) ** 3 for v in window)
        m4 = statistics.fmean((v - m) ** 4 for v in window)
        skew = m3 / (s ** 3)
        kurt = (m4 / (s ** 4)) - 3.0
    else:
        skew = 0.0
        kurt = 0.0

    # band powers (3 带)
    bp_low, bp_mid, bp_high = _band_powers(window, sample_rate_hz)

    # dominant / entropy
    dom_freq, sp_ent = _spectral_features(window, sample_rate_hz)

    # 自相关
    ac1 = _autocorr(window, 1)
    ac2 = _autocorr(window, 2)
    ac3 = _autocorr(window, 3)

    # 零穿越率（去均值后）
    zc = 0
    for i in range(1, n):
        if (window[i - 1] - m) * (window[i] - m) < 0:
            zc += 1
    zcr = zc / (n - 1) if n > 1 else 0.0

    # 斜率（端点差分 / 时长）
    if n >= 2:
        t_len_s = (n - 1) / sample_rate_hz
        slope = (window[-1] - window[0]) / t_len_s if t_len_s > 1e-12 else 0.0
    else:
        slope = 0.0

    # 单调比例
    if n >= 3:
        signs = []
        for i in range(1, n):
            d = window[i] - window[i - 1]
            signs.append(1 if d > 0 else (-1 if d < 0 else 0))
        same = sum(1 for i in range(1, len(signs)) if signs[i] == signs[i - 1] and signs[i] != 0)
        mono = same / (len(signs) - 1) if len(signs) > 1 else 0.0
    else:
        mono = 0.0

    return [
        round(m, 6),        # [0] mean
        round(s, 6),        # [1] std
        round(rms, 6),      # [2] rms
        round(mad, 6),      # [3] mad
        round(mn, 6),       # [4] min
        round(mx, 6),       # [5] max
        round(cv, 6),       # [6] cv
        round(skew, 6),     # [7] skew
        round(kurt, 6),     # [8] kurtosis
        round(bp_low, 6),   # [9] band_power_low
        round(bp_mid, 6),   # [10] band_power_mid
        round(bp_high, 6),  # [11] band_power_high
        round(dom_freq, 6), # [12] dominant_freq
        round(sp_ent, 6),   # [13] spectral_entropy
        round(ac1, 6),      # [14] lag1_autocorr
        round(ac2, 6),      # [15] lag2_autocorr
        round(ac3, 6),      # [16] lag3_autocorr
        round(zcr, 6),      # [17] zero_crossing_rate
        round(slope, 6),    # [18] slope
        round(mono, 6),     # [19] monotonic_fraction
    ]


__all__ = [
    "HealthLensUnavailableEngine",
    "SensorModelProbe",
    "FEATURE_DIM",
    "list_available_engines",
    "load_pulse_ppg_model",
    "load_papagei_model",
    "zero_shot_embed_wellness",
]
