"""边缘侧 EEG 频带功率计算（纯标准库）

为什么不用 numpy / scipy：边缘网关跑在树莓派 Zero 2 W 这类低配设备上，
预装一个 numpy 会把镜像体积和首次启动时间都拉爆。Goertzel 算法在 4 秒窗、
0.25Hz 分辨率下，单通道单帧大约 10^5 次浮点迭代，Python 纯循环足够实时。

正弦信号 x[n] = A*sin(2*pi*f0*n/fs) 的频点功率由 Goertzel 给出：
    P = (s1^2 + s2^2 - coeff*s1*s2) / N^2
其中 coeff = 2*cos(2*pi*f/fs)，N 为窗长样本数。
"""
from __future__ import annotations

import math

# 脑电经典频带划分（Hz）。与 Muse 官方/文献常用区间一致。
BANDS: dict[str, tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
}


def goertzel_power(samples, sample_rate: float, freq: float) -> float:
    """单频点归一化功率（Goertzel，O(N)）"""
    n = len(samples)
    if n == 0:
        return 0.0
    if not (0 < freq < sample_rate / 2):
        return 0.0
    coeff = 2.0 * math.cos(2.0 * math.pi * freq / sample_rate)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return (s1 * s1 + s2 * s2 - coeff * s1 * s2) / (n * n)


def band_powers(samples, sample_rate: float, bands: dict[str, tuple[float, float]] | None = None) -> dict[str, float]:
    """逐频带功率：在 [lo, hi] 内以窗长分辨率（1/window_seconds Hz）遍历整数频点累加"""
    bands = BANDS if bands is None else bands
    window_seconds = len(samples) / sample_rate if sample_rate else 0.0
    if window_seconds <= 0:
        return {name: 0.0 for name in bands}
    out: dict[str, float] = {}
    for name, (lo, hi) in bands.items():
        k_lo = max(1, int(math.ceil(lo * window_seconds)))
        k_hi = int(math.floor(hi * window_seconds))
        if k_hi < k_lo:
            k_hi = k_lo
        total = 0.0
        for k in range(k_lo, k_hi + 1):
            total += goertzel_power(samples, sample_rate, k / window_seconds)
        out[name] = total
    return out


def relative_band_powers(samples, sample_rate: float) -> dict[str, float]:
    """相对频带占比（各频带 / 全频段总和），无量纲，取值 0~1

    相对量比绝对功率更稳：Muse 的电极接触阻抗变化会让绝对幅度漂几个数量级，
    但各频带之间的比例关系基本守恒，所以八轴只吃相对占比。
    """
    powers = band_powers(samples, sample_rate)
    grand = sum(powers.values())
    if grand <= 0.0:
        return {name: 0.0 for name in powers}
    return {name: value / grand for name, value in powers.items()}
