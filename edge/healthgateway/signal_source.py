"""信号源抽象

三种源：
- MuseLslSource：InteraXon Muse 头环（Muse 2 / Muse S / 2016）—— muse-lsl 起 BLE 流，
  pylsl inlet 取样本，惰性依赖，没装 / 没蓝牙就只是 unavailable，不炸进程。
- ReplaySource：从 JSON 回放预采数据，无硬件也能跑通整条链路（过桥、演示、回归测试都靠它）。
- SyntheticSource：合成已知频点的信号，用来给频谱算法做真值验证。

统一输出：{"sample_rate": 256, "frames": {"TP9": [...], "AF7": [...], ...}}
"""
from __future__ import annotations

import json
import math
import random
import threading
from pathlib import Path

MUSE_CHANNELS = ("TP9", "AF7", "AF8", "TP10", "AUX")


class SignalSourceError(RuntimeError):
    """信号源不可用（缺依赖 / 没设备 / 设备离线）"""


class BaseSource:
    kind = "base"

    def __init__(self, sample_rate: int = 256):
        self.sample_rate = sample_rate
        self.channels: list[str] = []

    @property
    def available(self) -> bool:
        return True

    def read(self, seconds: float = 4.0) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        return None


class MuseLslSource(BaseSource):
    """Muse 头环。muselsl + pylsl 都是可选依赖"""

    kind = "muse_lsl"

    def __init__(self, sample_rate: int = 256, device_address: str | None = None, timeout: float = 8.0):
        super().__init__(sample_rate)
        self.device_address = device_address
        self.timeout = timeout
        self.channels = list(MUSE_CHANNELS[:4])
        self._stream_thread: threading.Thread | None = None
        self._inlet = None
        self._inlet_lock = threading.Lock()
        self._resolving = False

    @property
    def available(self) -> bool:
        return self._inlet is not None

    def _resolve_inlet(self) -> bool:
        """Musel 起流后要等 LSL 出口出现在网络里，再连 inlet"""
        if self._inlet is not None or self._resolving:
            return self._inlet is not None
        self._resolving = True
        try:
            import pylsl  # type: ignore[import-not-found]
            from muselsl import list_muses, stream  # type: ignore[import-not-found]

            muses = list_muses() if not self.device_address else [
                m for m in list_muses() if str(m.get("address", "")).lower() == self.device_address.lower()
            ]
            if not muses:
                return False
            address = muses[0].get("address")
            self._stream_thread = threading.Thread(target=stream, args=(address,), daemon=True)
            self._stream_thread.start()
            import time

            deadline = time.time() + self.timeout
            while time.time() < deadline:
                streams = pylsl.resolve_by-prop("type", "EEG", timeout=1.0)  # noqa: N802
                if streams:
                    self._inlet = pylsl.stream_inlet(streams[0], max_buflen=30, timeout=1.0)
                    return True
        except Exception:
            return False
        finally:
            self._resolving = False
        return False

    def read(self, seconds: float = 4.0) -> dict:
        if not self._resolve_inlet():
            raise SignalSourceError("muse-lsl 不可用：未安装 muselsl/pylsl，或扫描不到 Muse 设备")
        import time

        want = int(self.sample_rate * seconds)
        collected: dict[str, list] = {ch: [] for ch in self.channels}
        deadline = time.time() + self.timeout
        total = 0
        with self._inlet_lock:
            while total < want and time.time() < deadline:
                samples, _timestamps = self._inlet.pull_chunk(timeout=0.5, max_samples=1024)
                if not samples:
                    continue
                for name, buf in samples.items():
                    if name in collected:
                        collected[name].extend(buf)
                        total = max(total, len(collected[name]))
        return {"sample_rate": self.sample_rate, "frames": collected}

    def close(self) -> None:
        if self._inlet is not None:
            try:
                self._inlet.close_stream()
            except Exception:
                pass
            self._inlet = None


class ReplaySource(BaseSource):
    """从 JSON 回放：{"sample_rate": 256, "frames": {"TP9": [...]}}"""

    kind = "replay"

    def __init__(self, path: str | Path, sample_rate: int = 256):
        super().__init__(sample_rate)
        self.path = Path(path)
        self._data = json.loads(self.path.read_text(encoding="utf-8"))
        self.channels = list(self._data.get("frames", {}).keys()) or list(MUSE_CHANNELS[:4])

    def read(self, seconds: float = 4.0) -> dict:
        need = int(self.sample_rate * seconds)
        frames = {
            ch: self._data.get("frames", {}).get(ch, [])[:need] for ch in self.channels
        }
        return {"sample_rate": self.sample_rate, "frames": frames}


class SyntheticSource(BaseSource):
    """合成信号：已知成分，用来给频谱算法做真值验证"""

    kind = "synthetic"

    def __init__(self, sample_rate: int = 256, components: dict[str, float] | None = None, noise: float = 0.1):
        super().__init__(sample_rate)
        self.components = components or {"alpha": 1.0, "theta": 0.15}
        self.noise = noise
        self.channels = list(MUSE_CHANNELS[:4])

    def read(self, seconds: float = 4.0) -> dict:
        n = int(self.sample_rate * seconds)
        freqs = {"alpha": 10.0, "theta": 6.0, "beta": 20.0, "delta": 2.0}
        frames: dict[str, list] = {}
        for ch in self.channels:
            seq = []
            for i in range(n):
                value = 0.0
                for name, amp in self.components.items():
                    value += amp * math.sin(2 * math.pi * freqs[name] * i / self.sample_rate)
                seq.append(value + random.gauss(0.0, self.noise))
            frames[ch] = seq
        return {"sample_rate": self.sample_rate, "frames": frames}


def build_source(spec: dict) -> BaseSource:
    """按配置构建信号源"""
    kind = spec.get("kind", "synthetic")
    sample_rate = int(spec.get("sample_rate", 256))
    if kind == "muse_lsl":
        return MuseLslSource(sample_rate=sample_rate, device_address=spec.get("device_address"))
    if kind == "replay":
        return ReplaySource(spec["path"], sample_rate=sample_rate)
    return SyntheticSource(
        sample_rate=sample_rate,
        components=spec.get("components"),
        noise=float(spec.get("noise", 0.1)),
    )
