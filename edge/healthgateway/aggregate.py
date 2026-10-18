"""边缘侧指标聚合：原始采样 -> 日粒度健康指标

设计原则（跟八轴引擎的证据分级对齐）：
- 越靠近设备越只出「可证伪的原始量」，推导留给云端；
- 每个指标都带 sample_count / evidence 字段，云端能知道这条值有几分钟数据撑着；
- 单位一律用 SI 直觉量（比值无量纲、bpm、ms、count、percent），禁止自造单位。

命名规则：
- 能落到公开标准的（心率等）走 `loinc:` 语义由云端映射；
- 领域特有量（EEG 频带比、α 不对称）走 `hl.` 自有命名空间，**不冒充 LOINC**。
"""
from __future__ import annotations

import math

try:  # 以脚本方式 `python -m healthgateway.main` 运行时，包目录不在 sys.path 里
    from spectrum import relative_band_powers
except ImportError:
    from .spectrum import relative_band_powers

WINDOW_SECONDS = 4.0

# 云端能安全映射成 LOINC 的字段。仅在确有标准码时给出，缺码的一律走 hl.* 命名空间。
LOINC_HINTS: dict[str, tuple[str, str]] = {
    "resting_heart_rate": ("8867-4", "心率"),
}


def _finite_mean(values: list[float]) -> float:
    kept = [v for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return sum(kept) / len(kept) if kept else 0.0


def compute_band_metrics(frame: dict, window: float = WINDOW_SECONDS) -> dict:
    """一帧采样 -> {相对频带占比, alpha 不对称, 有效通道数}"""
    sample_rate = float(frame.get("sample_rate") or 256)
    frames = frame.get("frames") or {}
    channels = [ch for ch in frames if frames[ch]]
    if not channels:
        return {}

    rel: dict[str, float] = {}
    per_channel: dict[str, dict[str, float]] = {}
    for ch in channels:
        per_channel[ch] = relative_band_powers(frames[ch], sample_rate)

    keys = ["delta", "theta", "alpha", "beta"]
    agg: dict[str, float] = {}
    for key in keys:
        agg[key] = _finite_mean([per_channel[ch][key] for ch in channels])

    # 前额 α 不对称：ln(left_power) - ln(right_power)，Muse 上即 AF7 - AF8。
    # 正负号代表左右额叶激活偏向，是「神志/情绪负荷」类健康信号里最老牌的一个指标。
    asymmetry = 0.0
    if "AF7" in per_channel and "AF8" in per_channel:
        lf, rf = per_channel["AF7"].get("alpha", 0.0), per_channel["AF8"].get("alpha", 0.0)
        if lf > 0 and rf > 0:
            asymmetry = round(math.log(lf) - math.log(rf), 4)
    return {
        "channels": channels,
        "band_relative": {k: round(v or 0.0, 5) for k, v in agg.items()},
        "alpha_asymmetry": asymmetry,
        "channel_power": {ch: round(_finite_mean(list(per_channel[ch].values())), 6) for ch in channels},
    }


class MetricWindow:
    """时间窗累加器：把每帧的瞬时值滚成分钟级/日级稳定值"""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._bands: dict[str, list[float]] = {}
        self._asym: list[float] = []
        self._samples = 0

    def push(self, computed: dict) -> None:
        if not computed:
            return
        self._samples += 1
        for key, value in computed.get("band_relative", {}).items():
            self._bands.setdefault(key, []).append(float(value))
        if computed.get("alpha_asymmetry"):
            self._asym.append(float(computed["alpha_asymmetry"]))

    def flush(self) -> dict:
        """输出日粒度指标（同一天多次 flush 会被云端按最新值覆盖）"""
        metrics: list[dict] = []
        for key in sorted(self._bands):
            mean = _finite_mean(self._bands[key])
            if mean <= 0:
                continue
            metrics.append(
                {
                    "key": f"hl.eeg.{key}_ratio",
                    "value": round(mean, 5),
                    "unit": "ratio",
                    "evidence": "signal-derived",
                    "sample_count": len(self._bands[key]),
                }
            )
        if self._asym:
            metrics.append(
                {
                    "key": "hl.eeg.alpha_asymmetry",
                    "value": round(_finite_mean(self._asym), 5),
                    "unit": "log-ratio",
                    "evidence": "signal-derived",
                    "sample_count": len(self._asym),
                }
            )
        metrics.sort(key=lambda m: m["key"])
        return {
            "band_relative": {k: round(_finite_mean(v), 5) for k, v in sorted(self._bands.items())},
            "alpha_asymmetry": round(_finite_mean(self._asym), 5) if self._asym else 0.0,
            "frames": self._samples,
            "metrics": metrics,
        }


def build_payload(day: str, gateway_id: str, user_ref: str, metrics: dict, device: dict) -> dict:
    """拼出上报给 HealthLens 的 payload

    注意 payload 里不带任何身份敏感信息：user_ref 只是用户自己生成的绑定串，
    云端用它在自己的库里查用户，边缘设备不做账号体系。
    """
    return {
        "gateway_id": gateway_id,
        "user_ref": user_ref,
        "day": day,
        "device": device,
        "metrics": metrics.get("metrics", []),
        "stats": {
            "frames": metrics.get("frames", 0),
            "alpha_asymmetry": metrics.get("alpha_asymmetry", 0.0),
        },
    }
