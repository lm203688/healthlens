"""号脉硬件信号源（边缘侧）

负责把 PPG 波形（真实 ADC 或合成演示）转成 hl.pulse.* 特征，供 reporter 上送。

V0 用「合成波形 + 真实特征提取」让整条链路在没有实体硬件时也能端到端跑通；
真实硬件只需把 MAX30102 的 ADC 样本按同样接口喂给 extract_features 即可。
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any

WINDOW_SECONDS = 8.0
SAMPLE_RATE = 100.0  # Hz


def synthesize_ppg(rate_bpm: float = 72, profile: str = "normal",
                  seconds: float = WINDOW_SECONDS, sr: float = SAMPLE_RATE,
                  seed: int | None = None) -> list[float]:
    """生成一个心动周期叠加的 PPG 波形样本列表。

    profile 控制波形形态（对应脉象大类），用于演示而非临床。
    - normal: 健康基线的 h1/h3/h5 比例
    - xian(弦): h3 早现且偏高（血管张力高）
    - hong(洪): h1 大、h3/h1 低
    - se(涩): 重搏波弱、切迹模糊
    - hua(滑): h1 高且圆滑
    """
    rng = random.Random(seed)
    n = int(seconds * sr)
    samples = [0.0] * n
    cycle = 60.0 / max(rate_bpm, 1.0)
    cyc_samples = cycle * sr
    # 形态参数按 profile 调整（幅度差异用于区分洪/滑/平）
    a1 = 1.0
    a3_ratio = 0.6
    a5_ratio = 0.4
    dicrotic = 1.0
    if profile == "xian":
        a3_ratio, a5_ratio, dicrotic = 0.95, 0.35, 0.9
    elif profile == "hong":
        a1, a3_ratio, a5_ratio = 1.35, 0.30, 0.45
    elif profile == "se":
        a3_ratio, a5_ratio, dicrotic = 0.55, 0.12, 0.3
    elif profile == "hua":
        a1, a3_ratio, a5_ratio = 1.10, 0.50, 0.60
    for i in range(n):
        t = (i % cyc_samples) / sr  # 周期内时间
        # 叩击波 h1（主峰）
        w1 = 0.06 * cycle
        y = a1 * math.exp(-((t - 0.12 * cycle) / w1) ** 2)
        # 重搏前波 h3（潮汐波，约 1/3 周期）
        w3 = 0.10 * cycle
        y += a3_ratio * a1 * math.exp(-((t - 0.33 * cycle) / w3) ** 2)
        # 重搏波 h5（降支后，约 0.5 周期）
        w5 = 0.12 * cycle
        y += a5_ratio * a1 * dicrotic * math.exp(-((t - 0.5 * cycle) / w5) ** 2)
        # 轻微基线漂移 + 噪声
        y += 0.02 * math.sin(2 * math.pi * 0.2 * t) + rng.uniform(-0.01, 0.01)
        samples[i] = y
    return samples


def _local_maxima(values: list[float]) -> list[int]:
    return [i for i in range(1, len(values) - 1)
            if values[i] > values[i - 1] and values[i] >= values[i + 1]]


def _nms(peaks: list[int], values: list[float], min_dist: int) -> list[int]:
    """非极大值抑制：按高度降序贪心挑选，间距 >= min_dist 才保留。"""
    kept: list[int] = []
    for p in sorted(peaks, key=lambda i: -values[i]):
        if all(abs(p - k) >= min_dist for k in kept):
            kept.append(p)
    return sorted(kept)


# 振幅归一化参考（peak-to-baseline 幅度的典型量级），把 h1 映射到 ~[0,1]
_REF_AMP = 1.15
# 升支陡峭度参考（value/s），用于把斜率压到 [0,1]
_REF_SLOPE = 12.0


def extract_features(samples: list[float], sr: float = SAMPLE_RATE) -> dict[str, float]:
    """从波形提取 hl.pulse.* 特征（真实数据可用，无需 scipy）。

    主峰检测：局部极大且 > 0.5×全局最大，再用自适应最小间距 NMS 排除重搏前波 h3、
    重搏波 h5 等次级峰（避免脉率翻倍）。h3/h5 在各自心动周期窗口内取局部极大
    （pulse-matrix 法），并以周期内舒张末基线为基准计算相对振幅，故恒为正。
    """
    if not samples:
        return {}
    mean = sum(samples) / len(samples)
    c = [s - mean for s in samples]
    mx = max(c) if c else 0.0
    if mx <= 0:
        return {"hl.pulse.quality": 0.0}
    cands = [i for i in _local_maxima(c) if c[i] > 0.5 * mx]
    if len(cands) < 2:
        return {"hl.pulse.quality": 0.0}

    # 主峰检测：用 0.4s 绝对最小间距做 NMS，排除重搏前波 h3 / 重搏波 h5 等次级峰
    # （h3 出现在主峰后约 0.33 周期；在 40~200bpm 范围内其间距均 < 0.4s）。
    kept = _nms(cands, c, int(0.4 * sr))
    if len(kept) < 2:
        return {"hl.pulse.quality": 0.0}

    intervals = [(kept[i + 1] - kept[i]) / sr for i in range(len(kept) - 1)]
    if not intervals:
        return {"hl.pulse.quality": 0.0}
    # 丢弃明显异常的主峰间隔（<0.5× 或 >1.5× 中位周期）：多为重搏波混入或某拍主峰漏检，
    # 属检测伪差而非真实心律不齐，不计入脉率/节律。
    med_rr = sorted(intervals)[len(intervals) // 2]
    inliers = [iv for iv in intervals if 0.5 * med_rr <= iv <= 1.5 * med_rr]
    use = inliers if len(inliers) >= 2 else intervals
    mean_rr = sum(use) / len(use)
    rate = 60.0 / mean_rr if mean_rr > 0 else 0.0
    h1_raw = max(c[p] for p in kept)

    h3_list, h5_list, slope_list = [], [], []
    for i in range(len(kept) - 1):
        a, b = kept[i], kept[i + 1]
        cyc = b - a
        if cyc <= 2:
            continue
        seg = c[a:b + 1]
        baseline = min(seg) if seg else 0.0
        amp = (h1_raw - baseline) if (h1_raw - baseline) > 1e-6 else 1e-6
        # h3（重搏前波）：在 [0.20, 0.45] 周期内取局部极大
        lo3, hi3 = a + int(0.20 * cyc), min(b, a + int(0.45 * cyc))
        h3 = max(c[lo3:hi3 + 1]) if hi3 > lo3 else c[a]
        # h5（重搏波）：在降支的重搏区 [0.45, 0.80] 周期内取局部极大，
        # 排除临近下一心搏升支的伪峰
        lo5, hi5 = a + int(0.45 * cyc), b - max(int(0.15 * cyc), 2)
        h5 = max(c[lo5:hi5 + 1]) if hi5 > lo5 else baseline
        h3_list.append((h3 - baseline) / amp)
        h5_list.append((h5 - baseline) / amp)
        # 升支斜率：从升支起点（峰值前 0.12 周期）到峰值
        up_lo = max(a - int(0.12 * cyc), 0)
        if a - up_lo > 0:
            steep = (c[a] - c[up_lo]) / ((a - up_lo) / sr)
            slope_list.append(min(1.0, steep / _REF_SLOPE))

    h3_h1 = sum(h3_list) / len(h3_list) if h3_list else 0.0
    h5_h1 = sum(h5_list) / len(h5_list) if h5_list else 0.0
    ascending_slope = sum(slope_list) / len(slope_list) if slope_list else 0.0
    dicrotic_present = 1.0 if h5_h1 > 0.2 else 0.0

    if len(use) >= 2:
        cv = (max(use) - min(use)) / mean_rr if mean_rr > 0 else 0.0
        rhythm = max(0.0, 1.0 - cv * 2.0)
    else:
        rhythm = 1.0
    return {
        "hl.pulse.rate_bpm": round(rate, 1),
        "hl.pulse.h1": round(min(1.0, h1_raw / _REF_AMP), 3),
        "hl.pulse.h3_h1": round(h3_h1, 3),
        "hl.pulse.h5_h1": round(h5_h1, 3),
        "hl.pulse.dicrotic_present": dicrotic_present,
        "hl.pulse.ascending_slope": round(ascending_slope, 3),
        "hl.pulse.rhythm_regularity": round(rhythm, 3),
        "hl.pulse.pause_pattern": "none",
        "hl.pulse.perfusion_index": round(min(1.0, h1_raw / _REF_AMP), 3),
        "hl.pulse.sampling_hz": sr,
        "hl.pulse.quality": 1.0,
    }


class PulsePpgSource:
    """边缘脉冲源：每个 read() 返回一窗特征（dict）。"""

    def __init__(self, profile: str = "normal", sample_rate: float = SAMPLE_RATE,
                 noise: float = 0.0, seed: int | None = None):
        self.profile = profile
        self.sr = sample_rate
        self.noise = noise
        self.seed = seed

    def read(self, seconds: float = WINDOW_SECONDS) -> dict[str, Any]:
        rate = 72 if self.profile == "normal" else {
            "shu": 96, "chi": 54, "ji": 112, "xian": 74, "hong": 80,
            "se": 72, "hua": 76,
        }.get(self.profile, 72)
        samples = synthesize_ppg(rate_bpm=rate, profile=self.profile,
                                seconds=seconds, sr=self.sr, seed=self.seed)
        feats = extract_features(samples, self.sr)
        feats["hl.pulse.depth"] = ""  # V0 单点，无显式浮沉扫描
        return feats


class PulseSerialSource:
    """读取号脉固件(ESP32)经串口输出的聚合特征 JSON。

    固件每个采集窗（默认 8s）输出一行 ``{"hl.pulse.*": ...}``，本源按行解析后原样返回，
    不在边缘做二次特征提取（固件内已用 MAX30102 ADC 算好）。两种后端：
    - 真实串口：``port="COM3"`` / ``"/dev/ttyUSB0"``（需 pyserial，可选依赖，缺失不炸进程）；
    - 文件回放：``file="firmware_out.jsonl"``（无硬件也能验证整条链路，测试用）。

    与 PulsePpgSource 同接口（``read()`` 返回一窗特征 dict），``_collect_pulse`` 多窗平均逻辑不变。
    """

    def __init__(self, port: str | None = None, baudrate: int = 115200,
                 timeout: float = 10.0, file: str | None = None, sample_rate: float = 100.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.file = file
        self.sr = sample_rate
        self._ser = None
        self._fobj = None

    @property
    def available(self) -> bool:
        if self.file:
            return Path(self.file).is_file()
        try:
            import serial  # noqa: F401  lazy optional dep
        except Exception:
            return False
        return True

    def _open(self) -> None:
        if self.file:
            if self._fobj is None:
                self._fobj = open(self.file, encoding="utf-8")
            return
        if self._ser is None:
            import serial
            self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def _readline(self) -> str:
        self._open()
        if self.file:
            return self._fobj.readline() if self._fobj else ""
        return self._ser.readline().decode("utf-8", "ignore")

    def read(self, seconds: float = WINDOW_SECONDS) -> dict[str, Any]:
        deadline = time.time() + max(seconds, self.timeout)
        while time.time() < deadline:
            raw = self._readline()
            line = raw.strip()
            if not line:
                # 串口空读 = 超时，继续等；文件空读 = EOF，直接收尾
                if self.file:
                    return {"hl.pulse.quality": 0.0}
                continue
            if not line.startswith("{"):
                continue
            try:
                feats = json.loads(line)
            except Exception:
                continue
            feats = {k: v for k, v in feats.items() if k.startswith("hl.pulse.")}
            feats.setdefault("hl.pulse.quality", 1.0)
            return feats
        return {"hl.pulse.quality": 0.0}

    def close(self) -> None:
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self._fobj:
            try:
                self._fobj.close()
            except Exception:
                pass
            self._fobj = None


# ---------------------------------------------------------------------------
# EE 聚合器（Edge Gateway V1，#42）
# ---------------------------------------------------------------------------
# 设计动机：边缘盒子在弱网环境下每天推 24-48 次单条上报，每次开销（TLS 握手 +
# nonce 查询 + Redis SET）≈ 5-15KB。EE 聚合器把多次采集窗的特征合并成批量上报
# 格式，一次请求推给云端 /device-metrics/batch 端点，减少往返次数。
#
# 聚合策略：
#   - 数值型特征（rate_bpm/h1/h3_h1/h5_h1/ascending_slope/regularity/quality）：
#     多窗取中位数（抗偶发噪声）
#   - 二值型特征（dicrotic_present）：多窗取众数
#   - 字符串型特征（pause_pattern/depth）：保留最后一窗的值
#   - 元数据（sampling_hz）：取第一个窗的值
class PulseFeatureAggregator:
    """号脉特征多窗聚合器：把多次 read() 的特征合并成批量上报格式。"""

    # 需要取中位数的数值型特征
    _MEDIAN_KEYS = {
        "hl.pulse.rate_bpm",
        "hl.pulse.h1",
        "hl.pulse.h3_h1",
        "hl.pulse.h5_h1",
        "hl.pulse.ascending_slope",
        "hl.pulse.rhythm_regularity",
        "hl.pulse.quality",
        "hl.pulse.perfusion_index",
    }
    # 需要取众数的二值型特征
    _MODE_KEYS = {"hl.pulse.dicrotic_present"}
    # 保留最后一窗值的字符串型特征
    _LAST_KEYS = {"hl.pulse.pause_pattern", "hl.pulse.depth"}
    # 取第一个窗值的元数据
    _FIRST_KEYS = {"hl.pulse.sampling_hz"}

    def __init__(self, day: str | None = None):
        self.day = day or date.today().isoformat()
        self._windows: list[dict[str, Any]] = []
        self._window_start: float | None = None

    def add_window(self, features: dict[str, Any], timestamp: float | None = None) -> None:
        """添加一个采集窗的特征。"""
        ts = timestamp or time.time()
        # 自动检测跨天：如果新窗的时间戳与首窗差值超过 12 小时，认为跨天
        if self._window_start is not None and (ts - self._window_start) > 43200:
            # 跨天了，但 V1 不做跨天自动拆分（由调用方负责分 batch）
            pass
        if self._window_start is None:
            self._window_start = ts
        self._windows.append(features)

    def _median(self, values: list[float]) -> float:
        """中位数计算（纯标准库）。"""
        if not values:
            return 0.0
        sorted_vals = sorted(v for v in values if isinstance(v, (int, float)) and v == v)  # 过滤 NaN
        if not sorted_vals:
            return 0.0
        n = len(sorted_vals)
        return sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

    def _mode(self, values: list[float]) -> float:
        """众数计算（纯标准库）。"""
        if not values:
            return 0.0
        from collections import Counter
        c = Counter(v for v in values if isinstance(v, (int, float)))
        return c.most_common(1)[0][0]

    def flush(self) -> dict[str, Any]:
        """输出聚合后的特征 dict，可直接用于批量上报。"""
        if not self._windows:
            return {}

        agg: dict[str, Any] = {}

        # 数值型：中位数
        for key in self._MEDIAN_KEYS:
            vals = [w[key] for w in self._windows if key in w and isinstance(w[key], (int, float))]
            if vals:
                agg[key] = round(self._median(vals), 4)

        # 二值型：众数
        for key in self._MODE_KEYS:
            vals = [w[key] for w in self._windows if key in w and isinstance(w[key], (int, float))]
            if vals:
                agg[key] = round(self._mode(vals), 1)

        # 字符串型：最后一窗
        for key in self._LAST_KEYS:
            for w in reversed(self._windows):
                if key in w:
                    agg[key] = w[key]
                    break

        # 元数据：第一窗
        for key in self._FIRST_KEYS:
            for w in self._windows:
                if key in w:
                    agg[key] = w[key]
                    break

        # 添加聚合元数据
        agg["hl.pulse.aggregate_windows"] = len(self._windows)
        agg["hl.pulse.aggregate_seconds"] = round(self._windows[-1].get("_ts", time.time()) - self._window_start, 1) if self._window_start else 0.0

        return agg

    def to_batch_items(self, gateway_id: str, user_ref: str) -> list[dict[str, Any]]:
        """输出批量上报格式：[{day, metrics: [{key, value, unit, evidence, sample_count}]}]"""
        agg = self.flush()
        metrics = []
        for key, value in sorted(agg.items()):
            if key.startswith("hl.pulse.") and not key.endswith("_windows") and not key.endswith("_seconds"):
                metrics.append({
                    "key": key,
                    "value": value,
                    "unit": "ratio" if any(x in key for x in ["ratio", "_h1", "slope", "index", "regularity", "quality"]) else None,
                    "evidence": "edge-derived",
                    "sample_count": agg.get("hl.pulse.aggregate_windows", 1),
                })
        return [{
            "day": self.day,
            "device": {"type": "pulse", "label": "HealthLens 号脉终端 (PPG)"},
            "metrics": metrics,
            "stats": {
                "windows": agg.get("hl.pulse.aggregate_windows", 0),
                "aggregate_seconds": agg.get("hl.pulse.aggregate_seconds", 0.0),
            },
        }]

    def reset(self) -> None:
        """清空聚合器，开始新一轮采集。"""
        self._windows = []
        self._window_start = None
        self.day = date.today().isoformat()
