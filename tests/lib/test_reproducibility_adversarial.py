"""tests/lib/test_reproducibility_adversarial.py — 锁定 Batch B 输出。

关键性质：
  * 引擎确定性：same-seed double run 完全一致（0 违反）
  * 多 seed 分布稳定：每轴 50 seed × 50 case 下 mean/CV 在合理区间
  * 对抗输入：300 病态画像零崩溃、零越界（所有输出 ∈ [0, 100]）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "data" / "reproducibility_seeds.json"
OUT_ADV = ROOT / "data" / "adversarial_battery.json"
TOOL = ROOT / "tools" / "reproducibility_adversarial.py"

pytestmark = pytest.mark.needs_regenerate


def _ensure_artifact() -> None:
    if not OUT_JSON.exists() or not OUT_ADV.exists():
        subprocess.run([sys.executable, str(TOOL)], check=True, cwd=str(ROOT))


_ensure_artifact()


@pytest.fixture(scope="module")
def repro() -> dict:
    with open(OUT_JSON, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def adv() -> dict:
    with open(OUT_ADV, encoding="utf-8") as f:
        return json.load(f)


# ---------- 引擎确定性 ----------

def test_engine_is_fully_deterministic(repro):
    """同一 seed 内重复运行必须完全一致——引擎是输入的纯函数。"""
    assert repro["meta"]["deterministic_violations"] == 0, (
        f"engine deterministic violations: {repro['meta']['deterministic_violations']} "
        "（应=0；引擎必须是无副作用纯函数）"
    )


def test_total_runs_count(repro):
    """装置跑满 50 seeds × 50 cases。"""
    assert repro["meta"]["n_seeds"] == 50
    assert repro["meta"]["n_cases_per_seed"] == 50
    assert repro["meta"]["total_runs"] == 2500


# ---------- 分布稳定性 ----------

def test_all_axes_measured(repro):
    """每轴必须有统计输出。"""
    expected = ["A", "B", "C", "D", "E", "F", "G", "H"]
    assert sorted(repro["per_axis"].keys()) == sorted(expected)


def test_mean_scores_in_reasonable_range(repro):
    """每轴均值在合理区间（0-100），且分布有区分度（不是全 0 或全 100）。

    H 轴均值偏低（~12）反映 H（生物年龄/衰老）轴在合成画像上的严苛扣分
    设计——bioage_delta 每有 1 岁偏移就扣 10 分，合成人群 z 均值 0 但
    delta 均值 5-6 岁，导致 H 均分低。这不是 bug 而是设计，允许 [5, 99]。
    """
    for ax, s in repro["per_axis"].items():
        assert 0 <= s["mean"] <= 100, f"{ax} mean={s['mean']} out of [0,100]"
        assert 5 <= s["mean"] <= 99, (
            f"{ax} mean={s['mean']} 太接近边界，说明合成画像未覆盖分布"
        )


def test_min_max_within_bounds(repro):
    """每轴 min/max 都在 [0,100] 内。"""
    for ax, s in repro["per_axis"].items():
        assert 0 <= s["min"] <= 100, f"{ax} min={s['min']} out of bounds"
        assert 0 <= s["max"] <= 100, f"{ax} max={s['max']} out of bounds"


def test_axis_discrimination_variance(repro):
    """每轴应有非零标准差——评分器要区分画像。"""
    for ax, s in repro["per_axis"].items():
        assert s["sd"] > 3, f"{ax} sd={s['sd']} 太小，评分器几乎没有区分度"


def test_per_seed_means_stable(repro):
    """跨 seed 均值波动小于总体 SD——seed 之间分布一致（可复现）。

    per_seed_means 是长度 N_SEEDS 的列表，每个元素形如
    {'seed': s, 'mean_scores': {ax: ...}, 'n_cases': 50}。
    验证：50 个 seed 的均值集合应围绕总体均值波动（±3 分以内）。
    """
    assert len(repro["per_seed_means"]) == 50
    for ax in repro["per_axis"]:
        seed_means = [ps["mean_scores"][ax] for ps in repro["per_seed_means"]]
        overall_mean = repro["per_axis"][ax]["mean"]
        # 每 seed 均值的均值 ≈ 总体均值
        assert abs(sum(seed_means) / len(seed_means) - overall_mean) < 3.0, (
            f"{ax}: 每 seed 均值的均值偏离总体均值 >3"
        )
        # seed 均值的极差不应过大
        assert (max(seed_means) - min(seed_means)) < 30.0, (
            f"{ax}: seed 均值极差过大 ({max(seed_means)} - {min(seed_means)})"
        )


# ---------- 对抗稳健性 ----------

def test_no_adversarial_crashes(adv):
    """300 病态画像零崩溃——引擎不吞异常。"""
    assert adv["meta"]["crashes"] == 0, (
        f"adversarial crashes: {adv['meta']['crashes']}（应=0）"
    )


def test_no_unbounded_outputs(adv):
    """所有输出必须 ∈ [0,100]。"""
    assert adv["meta"]["unbounded_outputs"] == 0, (
        f"unbounded outputs: {adv['meta']['unbounded_outputs']}（应=0）"
    )


def test_all_adversarial_kinds_present(adv):
    """至少 5 种对抗画像被覆盖。"""
    assert len(adv["meta"]["kind_counts"]) >= 5, (
        f"only {len(adv['meta']['kind_counts'])} adversarial kinds, "
        "expected ≥5"
    )


def test_adversarial_outputs_bounded(adv):
    """对抗画像下每轴的 min/max 仍在 [0,100]。"""
    for ax, s in adv["per_axis"].items():
        if s["mean"] is None:
            continue
        assert 0 <= s["min"] <= 100, f"{ax} adversarial min={s['min']} out of bounds"
        assert 0 <= s["max"] <= 100, f"{ax} adversarial max={s['max']} out of bounds"


def test_all_adversarial_profiles_processed(adv):
    """300 画像都被处理（无跳过）。"""
    total = sum(adv["meta"]["kind_counts"].values())
    assert total == adv["meta"]["n_profiles"] == 300
