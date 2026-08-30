"""
HealthLens 硬件接入适配器 v0（"从容易的开始"）
================================================
把异构可穿戴/CGM/BCI 数据归一为「八轴时序样本」，是硬件架构 #61 §3 标准化层（八轴映射器）的可跑实现。

设计原则（对齐硬件架构 §1）：
  P1 授权可逆 · P2 本地优先 · P3 最小化 · P4 去标识 · P5 非诊疗

本文件提供：
  1. BiometricSample  —— 归一化样本
  2. CSVFileAdapter  —— 立即可跑：读模拟/导出的可穿戴 CSV → 八轴样本
  3. 平台 stub        —— 华为/Apple/GoogleFit/DexcomCGM/MuseEEG，含 §5 字段→轴映射与 OAuth TODO
                        （fetch() 待真实 OAuth/SDK，但"翻译核心"逻辑 field_map() 已定义）

用法见 tools/demo_ingest.py
"""
from __future__ import annotations
import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

# 八轴字母表（对齐理论体系 #57 / 硬件架构 §5）
AXES = ["A", "B", "C", "D", "E", "F", "G", "H"]
AXIS_NAMES = {
    "A": "气化", "B": "气血-线粒体", "C": "络脉-清瘀", "D": "阴阳-昼夜",
    "E": "脏腑-神经内分泌", "F": "正邪-炎症", "G": "神-情志", "H": "先天-肾精",
}

# 规范标记 → (轴, 单位)。覆盖硬件架构 §5 的平台标记示例。
MARKER_MAP = {
    # A 气化
    "postprandial_glucose_slope": ("A", "mmol/L/min"),
    "body_weight": ("A", "kg"),
    "ldl": ("A", "mg/dL"),
    # B 气血-线粒体
    "vo2max": ("B", "ml/kg/min"),
    "training_load": ("B", "au"),
    # D 阴阳-昼夜
    "sleep_midpoint": ("D", "clock"),
    "glucose_amplitude": ("D", "mg/dL"),
    "eating_window": ("D", "hours"),
    "sleep_efficiency": ("D", "%"),
    # E 脏腑-神经内分泌
    "stress_score": ("E", "au"),
    # F 正邪-炎症
    "resting_hr": ("F", "bpm"),
    # G 神-情志
    "hrv_rmssd": ("G", "ms"),
    "eeg_alpha_theta_ratio": ("G", "ratio"),
}


@dataclass
class BiometricSample:
    ts: str                 # ISO8601 时间戳
    axis: str              # A-H
    marker: str            # 规范标记
    value: float
    unit: str
    source: str            # 平台/设备
    raw: Optional[dict] = None

    def as_dict(self) -> dict:
        return asdict(self)


class BaseAdapter(ABC):
    """所有适配器的基类。fetch() 返回归一化八轴样本列表。"""

    platform: str = "base"

    @abstractmethod
    def fetch(self) -> list[BiometricSample]:
        ...

    @staticmethod
    def field_map() -> dict:
        """平台原始字段 → (规范标记, 轴, 单位)。子类覆盖。"""
        return {}

    def _to_sample(self, ts: str, raw_field: str, value: float, source: str) -> Optional[BiometricSample]:
        fmap = self.field_map()
        if raw_field not in fmap:
            return None
        marker, axis, unit = fmap[raw_field]
        return BiometricSample(ts=ts, axis=axis, marker=marker, value=value, unit=unit, source=source)


class CSVFileAdapter(BaseAdapter):
    """
    立即可跑的兜底适配器：读一份"宽表"可穿戴导出 CSV。
    CSV 列：date, resting_hr, hrv_rmssd, sleep_efficiency, sleep_midpoint, vo2max, body_weight, eating_window
    （缺失列忽略）。每行 → 多条八轴样本。
    """
    platform = "csv_import"

    # CSV 列名 → 规范标记（复用全局 MARKER_MAP 的键）
    _COL_TO_MARKER = {
        "resting_hr": "resting_hr",
        "hrv_rmssd": "hrv_rmssd",
        "sleep_efficiency": "sleep_efficiency",
        "sleep_midpoint": "sleep_midpoint",
        "vo2max": "vo2max",
        "body_weight": "body_weight",
        "eating_window": "eating_window",
    }

    def __init__(self, path: str, source: str = "wearable_csv"):
        self.path = path
        self.source = source

    def fetch(self) -> list[BiometricSample]:
        out: list[BiometricSample] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                date = row.get("date") or row.get("timestamp") or "1970-01-01"
                ts = _as_iso(date)
                for col, marker in self._COL_TO_MARKER.items():
                    if col in row and row[col] not in ("", None):
                        try:
                            val = float(row[col])
                        except ValueError:
                            continue
                        axis, unit = MARKER_MAP[marker]
                        out.append(BiometricSample(
                            ts=ts, axis=axis, marker=marker, value=val, unit=unit, source=self.source))
        return out


# ---------------- 平台 stub（fetch 待真实 OAuth/SDK，字段映射已定义） ----------------

class HuaweiHiHealthAdapter(BaseAdapter):
    """华为 HiHealth Kit。依赖 HMS Core + 华为健康 App 11.0.0.512+。
    TODO: 接 Java/Cloud/JS API，scope 仅申请八轴相关（HRV/睡眠/体重/血糖/血压），OAuth 用户授权。
    Extended Health Service Kit 支持实时心率订阅 + 体重/体脂回写（闭环）。"""
    platform = "huawei_hihealth"

    @staticmethod
    def field_map():
        return {"resting_heart_rate": "resting_hr", "hrv": "hrv_rmssd",
                "sleep_efficiency": "sleep_efficiency", "weight": "body_weight",
                "blood_glucose": "postprandial_glucose_slope"}

    def fetch(self):
        raise NotImplementedError("需华为 HiHealth OAuth/SDK；详见硬件架构 §2.1。field_map() 已定义翻译逻辑。")


class AppleHealthKitAdapter(BaseAdapter):
    """Apple HealthKit（iOS 原生）。TODO: 接 HealthKit 框架，scope 只读 HRV/睡眠/VO2max/CGM。"""
    platform = "apple_healthkit"

    @staticmethod
    def field_map():
        return {"HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_rmssd",
                "VO2Max": "vo2max", "SleepEfficiency": "sleep_efficiency"}

    def fetch(self):
        raise NotImplementedError("需 iOS HealthKit 集成；field_map() 已定义。")


class GoogleFitAdapter(BaseAdapter):
    """Google Fit / Health Connect（Android）。TODO: 接 Health Connect API，scope 活动/心率/睡眠/SpO2。"""
    platform = "google_fit"

    @staticmethod
    def field_map():
        return {"heart_rate": "resting_hr", "sleep_efficiency": "sleep_efficiency",
                "vo2max": "vo2max"}

    def fetch(self):
        raise NotImplementedError("需 Health Connect 集成；field_map() 已定义。")


class DexcomCGMAdapter(BaseAdapter):
    """Dexcom G7 / Libre 3 / Stelo CGM。TODO: 接 Dexcom API 或 Garmin 集成；MVP 允许 CSV 导出兜底。"""
    platform = "dexcom_cgm"

    @staticmethod
    def field_map():
        return {"postprandial_glucose_slope": "postprandial_glucose_slope",
                "glucose_amplitude": "glucose_amplitude"}

    def fetch(self):
        raise NotImplementedError("需 Dexcom/Libre API 或 CSV 导出；field_map() 已定义。")


class MuseEEGAdapter(BaseAdapter):
    """消费级 BCI/EEG（Muse/BrainBit 等）。TODO: 接蓝牙 SDK → α/θ 频段。仅趋势，不诊断。"""
    platform = "muse_eeg"

    @staticmethod
    def field_map():
        return {"alpha_theta_ratio": "eeg_alpha_theta_ratio"}

    def fetch(self):
        raise NotImplementedError("需 EEG SDK；field_map() 已定义。")


def _as_iso(d: str) -> str:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(d, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return datetime.now(timezone.utc).isoformat()


def summarize_by_axis(samples: list[BiometricSample]) -> dict:
    """按轴聚合样本数，供八轴趋势卡使用。"""
    out: dict[str, int] = {a: 0 for a in AXES}
    for s in samples:
        if s.axis in out:
            out[s.axis] += 1
    return out


if __name__ == "__main__":
    print("HealthLens biometric_ingest v0 — 八轴适配器库")
    print("可跑：CSVFileAdapter；stub：", [c.__name__ for c in
          (HuaweiHiHealthAdapter, AppleHealthKitAdapter, GoogleFitAdapter, DexcomCGMAdapter, MuseEEGAdapter)])
