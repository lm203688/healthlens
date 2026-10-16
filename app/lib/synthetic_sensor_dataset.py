"""合成传感器数据集（评测脚手架专用）

报告出处：《HealthLens_下一阶段全面提升报告_2026-10-08》§10 #6
> 「评测 Pulse-PPG / PaPaGei 在现有脉搏波数据上的零样本表征质量 | 3–5 天」

本模块用于把 §10 #6 从"待办"落成"可复现脚手架"：
- **仅用于评测脚手架验证**：生成确定性的合成 PPG / ECG / EMG / EEG 信号，
  让 harness 在**零真实权重**下也能跑通端到端流程，验证评测链路本身正确。
- **不用于生产健康推断**：合成波形与真人传感器数据分布差异极大，
  所有输出仅进入评测/测试路径，绝不进入八轴/脉象/融合引擎。

设计纪律：
1. **纯 Python**：用 `random.Random(seed)` 保证确定性；不依赖 numpy/scipy。
   若用户装了 numpy，本模块也不会因此走另一路径——输出保持可哈希一致。
2. **确定性**：同 (seed, params) 必产生同 signal；不同 seed 必产生不同 signal。
   便于 CI 快照断言 + 用户复现问题。
3. **分类可分**：三分类（静息 / 运动 / 应激）通过 HRV + 呼吸调制 + 波形参数
   显著区分，让 baseline 分类器能达到 ≥0.7 accuracy——验证 harness 可跑通，
   不假装合成数据能代表真实分布。

作者：HealthLens L2 表征层团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any


# ─────────────────────────── 常量 ───────────────────────────

SIGNAL_TYPES = ("PPG", "ECG", "EMG", "EEG")

# 三分类标签（"静息 / 运动 / 应激"），仅评测脚手架使用。
CLASS_LABELS = ("rest", "exercise", "stress")


# ─────────────────────────── 数据模型 ───────────────────────────

@dataclass
class SyntheticSensor:
    """合成传感器信号元数据 + 采样点。

    字段：
    - signal_type: PPG / ECG / EMG / EEG
    - sample_rate_hz: 采样率（Hz）
    - duration_sec: 信号持续时间（秒）
    - subject_id: 受试者 id（合成 ID，不做隐私 hash，仅评测用途）
    - samples: 采样点序列（长度 ≈ sample_rate_hz * duration_sec）
    - label: 三分类标签（rest / exercise / stress）或任务自定义标签
    - ground_truth_hr_bpm: 生成时的目标心率（回归任务用；非整数）
    """

    signal_type: str
    sample_rate_hz: float
    duration_sec: float
    subject_id: str
    samples: list[float] = field(default_factory=list)
    label: str = "rest"
    ground_truth_hr_bpm: float = 0.0

    def n_samples(self) -> int:
        return len(self.samples)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "SyntheticSensor":
        return SyntheticSensor(
            signal_type=d["signal_type"],
            sample_rate_hz=float(d["sample_rate_hz"]),
            duration_sec=float(d["duration_sec"]),
            subject_id=d["subject_id"],
            samples=list(d["samples"]),
            label=d.get("label", "rest"),
            ground_truth_hr_bpm=float(d.get("ground_truth_hr_bpm", 0.0)),
        )


@dataclass
class SyntheticSensorDataset:
    """合成数据集：批量生成 + 分类标签 + 序列化。

    用法：
        ds = SyntheticSensorDataset()
        sensors = ds.generate_batch(n=60, seed=42)
        payload = ds.to_json(sensors)  # str
        ds2 = SyntheticSensorDataset.from_json(payload)
    """

    sensors: list[SyntheticSensor] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.sensors)

    def labels(self) -> list[str]:
        return [s.label for s in self.sensors]

    def signal_types(self) -> set[str]:
        return {s.signal_type for s in self.sensors}

    def add(self, sensor: SyntheticSensor) -> None:
        self.sensors.append(sensor)

    def to_json(self, sensors: list[SyntheticSensor] | None = None) -> str:
        """序列化为确定性 JSON（键排序，缩进稳定）。"""
        targets = sensors if sensors is not None else self.sensors
        payload = {
            "schema": "synthetic_sensor_dataset.v1",
            "metadata": self.metadata,
            "sensors": [s.to_dict() for s in targets],
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def from_json(payload: str) -> "SyntheticSensorDataset":
        data = json.loads(payload)
        if data.get("schema") != "synthetic_sensor_dataset.v1":
            raise ValueError(f"unsupported dataset schema: {data.get('schema')!r}")
        ds = SyntheticSensorDataset(
            sensors=[SyntheticSensor.from_dict(s) for s in data["sensors"]],
            metadata=data.get("metadata", {}),
        )
        return ds

    def fingerprint(self) -> str:
        """内容指纹（sha256[:16]），便于 CI 快照断言。"""
        h = hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
        return h[:16]


# ─────────────────────────── 生成器（纯 Python） ───────────────────────────

def generate_ppg(
    n_samples: int = 500,
    freq_hz: float = 1.2,
    noise: float = 0.1,
    seed: int = 0,
    sample_rate_hz: float = 100.0,
    breath_mod: float = 0.05,
) -> list[float]:
    """生成合成 PPG 波形。

    构造：主正弦（心率基频 freq_hz ≈ 0.8–2.0 Hz）+ 呼吸调制（0.2 Hz 低幅）
    + 高斯噪声。波形形态对标野外脉搏波：主峰平滑、含次要重搏切迹。

    Args:
        n_samples: 样本点数
        freq_hz: 主频（心率基频，0.8–2.0 Hz 对应 48–120 BPM）
        noise: 高斯噪声强度（相对幅值）
        seed: 随机种子（相同 seed 相同输出）
        sample_rate_hz: 采样率（影响时间轴 t）
        breath_mod: 呼吸调制幅值（0.03–0.10）
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0, got {n_samples}")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
    if freq_hz <= 0:
        raise ValueError(f"freq_hz must be > 0, got {freq_hz}")
    rng = random.Random(seed)
    out: list[float] = []
    t_step = 1.0 / sample_rate_hz
    for i in range(n_samples):
        t = i * t_step
        # 主正弦：心搏主峰
        main = math.sin(2 * math.pi * freq_hz * t)
        # 呼吸调制（低频包络）
        breath = 1.0 + breath_mod * math.sin(2 * math.pi * 0.2 * t)
        # 高斯噪声
        n = noise * rng.gauss(0.0, 1.0)
        out.append(main * breath + n)
    return out


def generate_ecg(
    n_samples: int = 500,
    freq_hz: float = 1.2,
    noise: float = 0.05,
    seed: int = 0,
    sample_rate_hz: float = 250.0,
) -> list[float]:
    """生成合成 ECG 波形。

    构造：以 freq_hz 为心率基频，在每个心搏周期上叠加
    - P 波：小正峰（前 15% 周期位置）
    - QRS 复合波：Q 小负 + R 尖正峰 + S 小负（周期中部）
    - T 波：中等正峰（后 30% 周期位置）

    Args:
        n_samples: 样本点数
        freq_hz: 心率基频（0.8–2.0 Hz 对应 48–120 BPM）
        noise: 高斯噪声强度
        seed: 随机种子
        sample_rate_hz: 采样率（典型 250 Hz）
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0, got {n_samples}")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
    if freq_hz <= 0:
        raise ValueError(f"freq_hz must be > 0, got {freq_hz}")
    rng = random.Random(seed)
    t_step = 1.0 / sample_rate_hz
    period = 1.0 / freq_hz  # 每心动周期秒数
    out: list[float] = []
    for i in range(n_samples):
        t = i * t_step
        # 周期内归一化位置 0–1
        phase = (t % period) / period
        # 用一个高斯窗叠加 P/Q/R/S/T 5 个分量
        def _g(x: float, mu: float, sigma: float, amp: float) -> float:
            return amp * math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))
        p = _g(phase, 0.15, 0.03, 0.15)      # P 波
        q = _g(phase, 0.38, 0.015, -0.20)     # Q
        r = _g(phase, 0.42, 0.02, 1.0)        # R 峰
        s = _g(phase, 0.46, 0.015, -0.25)     # S
        tw = _g(phase, 0.65, 0.05, 0.30)      # T 波
        signal = p + q + r + s + tw
        signal += noise * rng.gauss(0.0, 1.0)
        out.append(signal)
    return out


def generate_emg(
    n_samples: int = 500,
    freq_hz: float = 20.0,
    noise: float = 0.5,
    seed: int = 0,
    sample_rate_hz: float = 500.0,
    activation: float = 1.0,
) -> list[float]:
    """生成合成 EMG 波形。

    构造：宽带高斯（EMG 特征）+ 可选肌电活动包络（activation > 1.0 时激活更强）。

    Args:
        n_samples: 样本点数
        freq_hz: 中心频率（EMG 通常在 10–500 Hz，默认 20 Hz 只是标记点）
        noise: 宽带噪声强度（EMG 主要成分）
        seed: 随机种子
        sample_rate_hz: 采样率（典型 500 Hz 起）
        activation: 肌电激活强度（1.0 = 基线，>1 = 更活跃）
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0, got {n_samples}")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
    rng = random.Random(seed)
    t_step = 1.0 / sample_rate_hz
    out: list[float] = []
    for i in range(n_samples):
        t = i * t_step
        # 宽频带高斯：EMG 主体
        wideband = noise * rng.gauss(0.0, 1.0)
        # 低频包络（肌电信号本身低频调制）
        envelope = math.sin(2 * math.pi * freq_hz * t) * 0.15 * activation
        out.append(wideband * activation + envelope)
    return out


def generate_eeg(
    n_samples: int = 1000,
    freq_hz: float = 10.0,
    noise: float = 0.1,
    seed: int = 0,
    sample_rate_hz: float = 250.0,
    band_alpha: float = 0.6,
    band_beta: float = 0.3,
    band_theta: float = 0.15,
) -> list[float]:
    """生成合成 EEG 波形。

    构造：α（8–13 Hz）+ β（13–30 Hz）+ θ（4–8 Hz）三个节律叠加 + 高斯噪声。
    α 是清醒放松时的主导节律，β 对应警觉/思维活动，θ 对应轻度困倦。

    Args:
        n_samples: 样本点数
        freq_hz: 参考频率（默认 10 Hz = α 主峰，影响 α 分量）
        noise: 高斯噪声强度
        seed: 随机种子
        sample_rate_hz: 采样率（典型 250 Hz 或 500 Hz）
        band_alpha: α 分量权重
        band_beta: β 分量权重
        band_theta: θ 分量权重
    """
    if n_samples <= 0:
        raise ValueError(f"n_samples must be > 0, got {n_samples}")
    if sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0, got {sample_rate_hz}")
    rng = random.Random(seed)
    t_step = 1.0 / sample_rate_hz
    alpha_f = max(8.0, min(13.0, freq_hz))  # α 主峰
    beta_f = alpha_f + 5.0                    # β 主峰（>α）
    theta_f = max(4.0, min(8.0, alpha_f - 3.0))  # θ 主峰（<α）
    out: list[float] = []
    for i in range(n_samples):
        t = i * t_step
        a = band_alpha * math.sin(2 * math.pi * alpha_f * t)
        b = band_beta * math.sin(2 * math.pi * beta_f * t + 0.3)
        th = band_theta * math.sin(2 * math.pi * theta_f * t + 0.7)
        n = noise * rng.gauss(0.0, 1.0)
        out.append(a + b + th + n)
    return out


# ─────────────────────────── 批量生成 ───────────────────────────

# 三分类参数预设：让不同标签在 HRV/波形特征上可显著区分
# - rest: 心率偏低（0.9 Hz = 54 BPM），呼吸调制适中，噪声小
# - exercise: 心率偏高（1.8 Hz = 108 BPM），呼吸调制强（喘息），噪声大
# - stress: 心率中等（1.3 Hz = 78 BPM），噪声最大（交感神经激活）
_CLASS_PRESETS: dict[str, dict[str, float]] = {
    "rest":     {"freq_hz": 0.9, "noise": 0.05, "breath_mod": 0.05},
    "exercise": {"freq_hz": 1.8, "noise": 0.15, "breath_mod": 0.12},
    "stress":   {"freq_hz": 1.3, "noise": 0.20, "breath_mod": 0.08},
}

# 各 signal_type 的默认参数（不同物理量有不同采样率与形态）
_SIGNAL_PRESETS: dict[str, dict[str, float]] = {
    "PPG": {"sample_rate_hz": 100.0},
    "ECG": {"sample_rate_hz": 250.0},
    "EMG": {"sample_rate_hz": 500.0, "freq_hz": 20.0},
    "EEG": {"sample_rate_hz": 250.0, "freq_hz": 10.0},
}


def _clamp_label(label: str) -> str:
    if label not in CLASS_LABELS:
        raise ValueError(f"unknown label {label!r}, expected one of {CLASS_LABELS}")
    return label


def generate_batch(
    n: int = 60,
    seed: int = 42,
    signal_type: str = "PPG",
    duration_sec: float = 5.0,
    labels: list[str] | None = None,
    subject_prefix: str = "subj",
) -> list[SyntheticSensor]:
    """批量生成合成传感器数据。

    标签默认按三分类均分轮转（rest / exercise / stress），也可显式传入。
    每个传感器有独立子 seed（seed * 1000 + idx），保证批次确定性。

    Args:
        n: 样本总数
        seed: 全局种子
        signal_type: PPG / ECG / EMG / EEG
        duration_sec: 每条信号时长（秒）
        labels: 每样本标签；None 时按 3 类均分轮转
        subject_prefix: subject_id 前缀

    Returns:
        list[SyntheticSensor]，长度 = n，标签按传入或轮转。
    """
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}")
    if signal_type not in SIGNAL_TYPES:
        raise ValueError(f"unknown signal_type {signal_type!r}, expected one of {SIGNAL_TYPES}")
    if duration_sec <= 0:
        raise ValueError(f"duration_sec must be > 0, got {duration_sec}")

    if labels is None:
        labels = [CLASS_LABELS[i % len(CLASS_LABELS)] for i in range(n)]
    elif len(labels) != n:
        raise ValueError(f"labels length {len(labels)} != n {n}")
    for lab in labels:
        _clamp_label(lab)

    preset = dict(_SIGNAL_PRESETS[signal_type])
    sensors: list[SyntheticSensor] = []
    for idx in range(n):
        lab = labels[idx]
        class_params = dict(_CLASS_PRESETS[lab])
        # EMG / EEG 的 freq_hz 使用类型预设（不用心率参数）
        if signal_type in ("EMG", "EEG"):
            class_params["freq_hz"] = preset.get("freq_hz", 10.0)
        sr = preset["sample_rate_hz"]
        n_samples = int(round(sr * duration_sec))
        sub_seed = seed * 1000 + idx
        if signal_type == "PPG":
            samples = generate_ppg(
                n_samples=n_samples,
                freq_hz=class_params.get("freq_hz", 1.2),
                noise=class_params.get("noise", 0.1),
                seed=sub_seed,
                sample_rate_hz=sr,
                breath_mod=class_params.get("breath_mod", 0.05),
            )
        elif signal_type == "ECG":
            samples = generate_ecg(
                n_samples=n_samples,
                freq_hz=class_params.get("freq_hz", 1.2),
                noise=class_params.get("noise", 0.05),
                seed=sub_seed,
                sample_rate_hz=sr,
            )
        elif signal_type == "EMG":
            samples = generate_emg(
                n_samples=n_samples,
                freq_hz=preset.get("freq_hz", 20.0),
                noise=class_params.get("noise", 0.5) + 0.3,
                seed=sub_seed,
                sample_rate_hz=sr,
                activation=1.0 + (0.5 if lab == "exercise" else 0.3 if lab == "stress" else 0.0),
            )
        else:  # EEG
            # EEG 节律按标签微调：rest 偏 α、exercise 偏 β、stress 偏 θ
            band_alpha = 0.6 if lab == "rest" else 0.4
            band_beta = 0.4 if lab == "exercise" else 0.3
            band_theta = 0.3 if lab == "stress" else 0.15
            samples = generate_eeg(
                n_samples=n_samples,
                freq_hz=10.0,
                noise=class_params.get("noise", 0.1) + 0.05,
                seed=sub_seed,
                sample_rate_hz=sr,
                band_alpha=band_alpha,
                band_beta=band_beta,
                band_theta=band_theta,
            )
        gt_hr = class_params.get("freq_hz", 1.0) * 60.0
        sensors.append(SyntheticSensor(
            signal_type=signal_type,
            sample_rate_hz=sr,
            duration_sec=duration_sec,
            subject_id=f"{subject_prefix}_{sub_seed:06d}",
            samples=samples,
            label=lab,
            ground_truth_hr_bpm=gt_hr,
        ))
    return sensors


__all__ = [
    "SIGNAL_TYPES",
    "CLASS_LABELS",
    "SyntheticSensor",
    "SyntheticSensorDataset",
    "generate_ppg",
    "generate_ecg",
    "generate_emg",
    "generate_eeg",
    "generate_batch",
]
