"""给频谱算法做真值验证：合成一段已知成分的信号，看相对频带占比落得对不对。

这是本项目里少见的不吃 mock 的测试 —— 合成信号是确定性的（噪声为 0），
如果 Goertzel 实现写歪了，alpha 占比立刻掉下去，跑不过。
"""
import math
import os
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("HL_EDGE_DATA_DIR", str(Path(__file__).resolve().parents[1] / "var"))

from aggregate import MetricWindow, compute_band_metrics  # noqa: E402
from signal_source import SyntheticSource  # noqa: E402
from spectrum import band_powers, goertzel_power, relative_band_powers  # noqa: E402

SAMPLE_RATE = 256


def sine(freq: float, seconds: float = 4.0, amp: float = 1.0, rate: int = SAMPLE_RATE):
    n = int(rate * seconds)
    return [amp * math.sin(2 * math.pi * freq * i / rate) for i in range(n)]


class TestSpectrum(unittest.TestCase):
    def test_pure_sine_lands_in_its_band(self):
        x = sine(10.0)  # alpha
        powers = band_powers(x, SAMPLE_RATE)
        # alpha 窗应该显著压过 theta、beta
        self.assertGreater(powers["alpha"], powers["theta"] * 3.0)
        self.assertGreater(powers["alpha"], powers["beta"] * 3.0)

    def test_goertzel_matches_analytic_power(self):
        """解析对照：x[n]=A·sin(2πf₀n/fs)，且 f₀ 恰好落在整数 bin（f₀·N/fs 为整数）时，
        Goertzel 结果除以 N² 等于 |X[k]|²/N² = (A·N/2)² / N² = A²/4。
        10Hz × 1024 / 256Hz = 40，是整数 bin，所以理论值就是 A²/4 = 0.25。"""
        amp = 1.0
        x = sine(10.0, seconds=4.0, amp=amp)
        power = goertzel_power(x, SAMPLE_RATE, 10.0)
        expected = amp ** 2 / 4.0
        self.assertAlmostEqual(power, expected, delta=expected * 0.02)

    def test_relative_sums_to_one(self):
        base = sine(6.0, amp=0.5)
        noisy = [v + random.gauss(0.0, 0.2) for v in base]
        rel = relative_band_powers(noisy, SAMPLE_RATE)
        total = sum(rel.values())
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_empty_input_is_safe(self):
        self.assertEqual(relative_band_powers([], SAMPLE_RATE), {k: 0.0 for k in ("delta", "theta", "alpha", "beta")})


class TestAggregate(unittest.TestCase):
    def test_alpha_dominant_signal_flags_as_alpha(self):
        source = SyntheticSource(sample_rate=SAMPLE_RATE, components={"alpha": 1.0}, noise=0.0)
        frame = source.read(seconds=4.0)
        computed = compute_band_metrics(frame)
        rel = computed["band_relative"]
        self.assertGreater(rel["alpha"], rel["theta"])
        self.assertGreater(rel["alpha"], rel["beta"])

    def test_window_accumulates_and_flushes(self):
        source = SyntheticSource(sample_rate=SAMPLE_RATE, components={"alpha": 1.0, "theta": 0.2}, noise=0.0)
        window = MetricWindow()
        for _ in range(3):
            window.push(compute_band_metrics(source.read(seconds=4.0)))
        flushed = window.flush()
        self.assertEqual(flushed["frames"], 3)
        keys = {m["key"] for m in flushed["metrics"]}
        self.assertIn("hl.eeg.alpha_ratio", keys)
        self.assertTrue(all(0.0 <= m["value"] <= 1.0 for m in flushed["metrics"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
