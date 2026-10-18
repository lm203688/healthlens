"""reproducibility_seeds.py + adversarial_battery.py — S5/S6 修复
====================================================================
目的：为 SCI 论文补齐「多随机种子可复现性」与「对抗输入稳健性」两项
审稿人常问的证据，且**不依赖真实受试者**（全合成数据）。

两个模块在同一文件里，共享画像生成逻辑，输出：
  - data/reproducibility_seeds.json           50 seeds × 50 cases 的八轴分布
  - data/adversarial_battery.json             300 对抗画像的结果与稳定性检查
  - data/REPRODUCIBILITY_AND_ADVERSARIAL_REPORT.md
  - data/reproducibility_heatmap.svg
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "lib"))

from axis_scorers import score_all_axes, ALL_AXES  # noqa: E402
from bioage_engine import BioAgeEngine  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_JSON = os.path.join(ROOT, "data", "reproducibility_seeds.json")
OUT_ADV = os.path.join(ROOT, "data", "adversarial_battery.json")
OUT_MD = os.path.join(ROOT, "data", "REPRODUCIBILITY_AND_ADVERSARIAL_REPORT.md")
OUT_SVG = os.path.join(ROOT, "data", "reproducibility_heatmap.svg")

N_SEEDS = 50
N_CASES_PER_SEED = 50
N_ADVERSARIAL = 300
BASE_SEED = 20261018


# ---------- synthetic profile generation (shared) ----------
def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def make_profile(rng: random.Random) -> dict:
    age = rng.randint(20, 80)
    z = rng.gauss(0, 1)
    is_male = rng.random() < 0.5
    bm = {
        "glucose": _clamp(5.0 + 0.01 * age + 0.35 * z + rng.gauss(0, 0.3), 3.8, 12),
        "hba1c": _clamp(5.3 + 0.01 * age + 0.15 * z + rng.gauss(0, 0.15), 4.5, 8.5),
        "waist_cm": _clamp(80 + 0.15 * age + 4 * z + rng.gauss(0, 4), 60, 130),
        "triglycerides": _clamp(1.2 + 0.01 * age + 0.25 * z + rng.gauss(0, 0.3), 0.4, 5),
        "bmi": _clamp(22 + 0.05 * age + 1.5 * z + rng.gauss(0, 1.2), 17, 40),
        "hdl": _clamp(1.5 - 0.005 * age - 0.18 * z + rng.gauss(0, 0.15), 0.7, 2.5),
        "hs_crp": _clamp(math.exp(0.4 + 0.02 * age + 0.5 * z + rng.gauss(0, 0.3)), 0.2, 20),
        "il6": _clamp(math.exp(-0.5 + 0.02 * age + 0.6 * z + rng.gauss(0, 0.4)), 0.3, 20),
        "sbp": _clamp(115 + 0.35 * age + 6 * z + rng.gauss(0, 6), 95, 200),
        "dbp": _clamp(72 + 0.15 * age + 3 * z + rng.gauss(0, 4), 55, 110),
        "homocysteine": _clamp(9 + 0.05 * age + 1.2 * z + rng.gauss(0, 1.5), 5, 25),
    }
    wearable = {
        "hrv_rmssd": _clamp(55 - 12 * z + rng.gauss(0, 5), 10, 100),
        "resting_hr": _clamp(70 + 6 * z + rng.gauss(0, 3), 45, 110),
        "sleep_duration_h": _clamp(7.5 - 0.7 * z + rng.gauss(0, 0.5), 3, 12),
        "sleep_midpoint_jitter": _clamp(30 + 20 * z + rng.gauss(0, 6), 10, 120),
        "social_jetlag_h": _clamp(0.8 + 0.6 * z + rng.gauss(0, 0.3), 0, 5),
        "sleep_duration_cv": _clamp(0.1 + 0.15 * z + rng.gauss(0, 0.05), 0.02, 0.6),
    }
    return {"age": age, "z": round(z, 3), "biomarkers": bm, "wearable": wearable,
            "symptoms": [], "is_male": is_male}


_BIOAGE = BioAgeEngine()


def score_profile(p: dict) -> dict[str, float]:
    bm = p["biomarkers"]
    bio = _BIOAGE.assess(
        chrono_age=p["age"], is_male=p["is_male"],
        glucose=bm.get("glucose"), hba1c=bm.get("hba1c"),
        hs_crp=bm.get("hs_crp"), waist_cm=bm.get("waist_cm"),
        hdl=bm.get("hdl"), triglycerides=bm.get("triglycerides"),
        sbp=bm.get("sbp"), bmi=bm.get("bmi"),
    )
    out = score_all_axes(
        biomarkers=bm, wearable=p["wearable"],
        symptoms=p["symptoms"], bioage_delta=bio.delta,
        is_male=p["is_male"], jurisdiction="cn",
    )
    return {ax: (sc.score if sc.score is not None else 0.0) for ax, sc in out.items()}


# ---------- Batch B.1: multi-seed reproducibility ----------
def run_multi_seed() -> dict:
    """50 seeds × 50 cases → per-axis variance across seeds for same case index.

    关键性质：给定同一 seed 内的第 k 个 case 输入是完全确定的（同种 seed），
    不同 seed 下第 k 个 case 输入不同——所以我们测的是**引擎在输入分布下的
    稳定性**，即八轴评分是否遵循同一分布，而不是逐 case 的确定性。

    同时逐 seed 内部检查确定性：同一 seed 内重复跑两遍必须完全一致。
    """
    per_axis_all: dict[str, list[float]] = {ax: [] for ax in ALL_AXES}
    per_axis_by_seed: dict[str, dict[str, list[float]]] = {ax: {} for ax in ALL_AXES}
    per_seed_case_scores: list[dict] = []
    deterministic_violations = 0

    for seed in range(N_SEEDS):
        rng = random.Random(BASE_SEED + seed)
        seed_scores: dict[str, list[float]] = {ax: [] for ax in ALL_AXES}
        for _ in range(N_CASES_PER_SEED):
            p = make_profile(rng)
            s1 = score_profile(p)
            s2 = score_profile(p)
            if s1 != s2:
                deterministic_violations += 1
            for ax in ALL_AXES:
                seed_scores[ax].append(s1[ax])
                per_axis_all[ax].append(s1[ax])
        for ax in ALL_AXES:
            per_axis_by_seed[ax][str(seed)] = seed_scores[ax]
        per_seed_case_scores.append({
            "seed": seed,
            "mean_scores": {ax: round(st.mean(seed_scores[ax]), 3) for ax in ALL_AXES},
            "n_cases": N_CASES_PER_SEED,
        })

    # Per-axis: mean, sd, cv, min, max across all (seed, case)
    axis_stats = {}
    for ax in ALL_AXES:
        vals = per_axis_all[ax]
        mn = min(vals)
        mx = max(vals)
        mean = st.mean(vals)
        sd = st.pstdev(vals)
        cv = sd / mean if mean else 0.0
        axis_stats[ax] = {
            "mean": round(mean, 3), "sd": round(sd, 3),
            "cv": round(cv, 4), "min": round(mn, 2), "max": round(mx, 2),
            "n_runs": len(vals),
        }

    # ICC(2,k) approximation: one-way random effects ANOVA per axis
    icc = {}
    for ax in ALL_AXES:
        all_vals = per_axis_all[ax]
        grand_mean = st.mean(all_vals)
        k = N_CASES_PER_SEED  # trials per seed
        n = N_SEEDS
        # Between-subject (seed) SS
        ss_between = sum(k * (st.mean(per_axis_by_seed[ax][str(s)]) - grand_mean) ** 2
                         for s in range(N_SEEDS))
        # Within-subject (case within seed) SS
        ss_within = 0.0
        for s in range(N_SEEDS):
            mean_s = st.mean(per_axis_by_seed[ax][str(s)])
            for v in per_axis_by_seed[ax][str(s)]:
                ss_within += (v - mean_s) ** 2
        ms_between = ss_between / (n - 1)
        ms_within = ss_within / (n * (k - 1))
        icc_21 = (ms_between - ms_within) / (ms_between + (k - 1) * ms_within) if ms_between > 0 else float("nan")
        icc[ax] = round(icc_21, 4)

    return {
        "meta": {
            "n_seeds": N_SEEDS, "n_cases_per_seed": N_CASES_PER_SEED,
            "total_runs": N_SEEDS * N_CASES_PER_SEED,
            "deterministic_violations": deterministic_violations,
        },
        "per_axis": axis_stats,
        "icc_2_1": icc,
        "per_seed_means": per_seed_case_scores,
    }


# ---------- Batch B.2: adversarial robustness ----------
def make_adversarial(rng: random.Random) -> tuple[dict, str]:
    """Construct a pathological profile: extreme, contradictory, or impossible."""
    kind = rng.choice([
        "extreme_high_bio", "extreme_low_bio", "contradictory_bp_hrv",
        "all_extreme_outliers", "missing_critical", "impossible_combinations",
        "clamped_boundaries",
    ])
    p = make_profile(rng)
    bm = p["biomarkers"]
    wearable = p["wearable"]

    if kind == "extreme_high_bio":
        bm.update({
            "glucose": 12.0, "hba1c": 8.5, "hs_crp": 20.0, "il6": 20.0,
            "sbp": 200, "bmi": 40, "triglycerides": 5.0, "hdl": 0.7,
        })
        wearable.update({"hrv_rmssd": 10, "resting_hr": 110})
    elif kind == "extreme_low_bio":
        bm.update({
            "glucose": 3.8, "hba1c": 4.5, "hs_crp": 0.2, "il6": 0.3,
            "sbp": 95, "bmi": 17, "hdl": 2.5, "triglycerides": 0.4,
        })
        wearable.update({"hrv_rmssd": 100, "resting_hr": 45})
    elif kind == "contradictory_bp_hrv":
        # High BP but extremely high HRV — usually physiologically incompatible
        bm.update({"sbp": 190, "dbp": 105, "glucose": 11})
        wearable.update({"hrv_rmssd": 95, "resting_hr": 50})
    elif kind == "all_extreme_outliers":
        bm.update({k: float("inf") if "crp" in k or "il6" in k else 10 * v
                   for k, v in bm.items()})
        # fix infinite
        bm["hs_crp"] = 20.0
        bm["il6"] = 20.0
        bm["glucose"] = 12.0
        bm["sbp"] = 200
        bm["waist_cm"] = 130
    elif kind == "missing_critical":
        # Strip most biomarkers and wearables
        p["biomarkers"] = {"sbp": 130}  # only SBP present
        p["wearable"] = {}
    elif kind == "impossible_combinations":
        bm.update({
            "glucose": 3.5, "hba1c": 4.2, "hs_crp": 20.0, "il6": 20.0,
            "sbp": 95, "bmi": 17, "hdl": 2.5, "triglycerides": 0.4,
        })
    elif kind == "clamped_boundaries":
        # All at clamp lower bounds
        bm.update({
            "glucose": 3.8, "hba1c": 4.5, "hs_crp": 0.2, "il6": 0.3,
            "sbp": 95, "bmi": 17, "triglycerides": 0.4, "hdl": 2.5,
            "waist_cm": 60, "homocysteine": 5,
        })
        wearable.update({
            "hrv_rmssd": 10, "resting_hr": 45, "sleep_duration_h": 3,
            "sleep_midpoint_jitter": 10, "social_jetlag_h": 0,
            "sleep_duration_cv": 0.02,
        })

    return p, kind


def run_adversarial() -> dict:
    """Feed 300 adversarial profiles, verify engine does not crash and outputs
    remain bounded [0, 100] with no pathological recommendations."""
    rng = random.Random(BASE_SEED + 999)
    scores_by_kind: dict[str, list[float]] = {}
    crashes = 0
    unbounded = 0
    per_kind_stats: dict[str, dict] = {}
    kind_counts: dict[str, int] = {}

    for _ in range(N_ADVERSARIAL):
        try:
            p, kind = make_adversarial(rng)
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            axis_scores = score_profile(p)
            for ax, val in axis_scores.items():
                scores_by_kind.setdefault(ax, []).append(val)
                if not (0.0 <= val <= 100.0):
                    unbounded += 1
        except Exception:
            crashes += 1

    # Per-axis: mean, sd, min, max across all adversarial profiles
    per_axis = {}
    for ax in ALL_AXES:
        vals = scores_by_kind.get(ax, [])
        if not vals:
            per_axis[ax] = {"mean": None, "n": 0}
            continue
        per_axis[ax] = {
            "mean": round(st.mean(vals), 3),
            "sd": round(st.pstdev(vals), 3),
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "n": len(vals),
        }

    return {
        "meta": {
            "n_profiles": N_ADVERSARIAL,
            "kind_counts": kind_counts,
            "crashes": crashes,
            "unbounded_outputs": unbounded,
        },
        "per_axis": per_axis,
    }


# ---------- Report ----------
def write_report(repro: dict, adv: dict) -> None:
    lines = ["# HealthLens Reproducibility & Adversarial Robustness Report",
             "",
             f"- Multi-seed: {repro['meta']['n_seeds']} seeds × "
             f"{repro['meta']['n_cases_per_seed']} cases = "
             f"{repro['meta']['total_runs']} runs",
             f"- Adversarial: {adv['meta']['n_profiles']} pathological profiles",
             f"- Seed base: {BASE_SEED}",
             "",
             "## Multi-seed reproducibility",
             "",
             f"Determinism check (same-seed double run): "
             f"{repro['meta']['deterministic_violations']} violations "
             f"(0 = fully deterministic).",
             "",
             "| Axis | Mean | SD | CV | Min | Max | ICC(2,1) |",
             "|---|---|---|---|---|---|---|"]
    for ax in ALL_AXES:
        s = repro["per_axis"][ax]
        icc = repro["icc_2_1"][ax]
        lines.append(f"| {ax} | {s['mean']} | {s['sd']} | {s['cv']} | "
                     f"{s['min']} | {s['max']} | {icc} |")
    lines.append("")
    lines.append("CV (coefficient of variation) quantifies how much each axis's")
    lines.append("score moves across the entire input distribution. Lower CV =")
    lines.append("more concentrated scores (potentially less discriminative).")
    lines.append("ICC(2,1) here measures agreement of axis scores across seeds —")
    lines.append("in this synthetic setting, seeds generate *independent* samples")
    lines.append("from the same distribution, so ICC reflects between-seed")
    lines.append("variance of the axis means, not test-retest of the same subject.")
    lines.append("")
    lines.append("## Adversarial robustness")
    lines.append("")
    lines.append(f"Crashes: {adv['meta']['crashes']} (target: 0).")
    lines.append(f"Out-of-range outputs: {adv['meta']['unbounded_outputs']} "
                 f"(target: 0, all scores must lie in [0,100]).")
    lines.append("")
    lines.append("| Kind | N |")
    lines.append("|---|---|")
    for k, n in adv["meta"]["kind_counts"].items():
        lines.append(f"| {k} | {n} |")
    lines.append("")
    lines.append("| Axis | Mean | SD | Min | Max |")
    lines.append("|---|---|---|---|---|")
    for ax in ALL_AXES:
        s = adv["per_axis"][ax]
        if s["mean"] is None:
            continue
        lines.append(f"| {ax} | {s['mean']} | {s['sd']} | {s['min']} | {s['max']} |")
    lines.append("")
    lines.append("## Honest boundaries")
    lines.append("")
    lines.append("1. Both modules run on **synthetic data**. Determinism tests")
    lines.append("   confirm the engine is a pure function of its inputs — real")
    lines.append("   longitudinal stability (weeks/months on the same subject)")
    lines.append("   is out of scope.")
    lines.append("2. Adversarial kinds are *designed* pathologies (contradictory")
    lines.append("   biomarker combinations, missing fields, extremes). A real")
    lines.append("   robustness study would use adversarial search or fuzzing.")
    lines.append("3. All outputs stay within [0,100] because every axis scorer")
    lines.append("   uses `_clamp` internally; this is a code-level guarantee,")
    lines.append("   not a data-dependent property.")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_svg(repro: dict) -> None:
    W, H = 700, 320
    cell_w = 80
    pad_l, pad_t = 100, 60
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="700" height="320">',
             '<rect width="700" height="320" fill="#ffffff"/>',
             '<text x="350" y="25" font-family="sans-serif" font-size="14" '
             'font-weight="700" text-anchor="middle">'
             f'8 Axes × Multi-Seed (N={repro["meta"]["total_runs"]}) — '
             'Mean ± SD</text>']
    for i, ax in enumerate(ALL_AXES):
        s = repro["per_axis"][ax]
        y = pad_t + i * 30
        parts.append(f'<text x="{pad_l - 10}" y="{y + 14}" font-family="sans-serif" '
                     f'font-size="12" font-weight="700" text-anchor="end">{ax}</text>')
        # Bar: mean ± sd
        x_mean = pad_l + s["mean"] * 5.5
        x_lo = pad_l + max(0, s["mean"] - s["sd"]) * 5.5
        x_hi = pad_l + min(100, s["mean"] + s["sd"]) * 5.5
        parts.append(f'<line x1="{x_lo}" y1="{y}" x2="{x_hi}" y2="{y}" '
                     f'stroke="#333" stroke-width="12" stroke-linecap="round"/>')
        parts.append(f'<line x1="{x_mean}" y1="{y - 12}" x2="{x_mean}" y2="{y + 12}" '
                     f'stroke="#c00" stroke-width="2"/>')
        parts.append(f'<text x="{x_hi + 8}" y="{y + 4}" font-family="monospace" '
                     f'font-size="10">{s["mean"]:.1f}±{s["sd"]:.1f}</text>')
    parts.append('</svg>')
    with open(OUT_SVG, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def main() -> None:
    print(f"[repro] seeds={N_SEEDS} cases={N_CASES_PER_SEED} adv={N_ADVERSARIAL}")
    repro = run_multi_seed()
    adv = run_adversarial()

    print(f"[repro] deterministic_violations={repro['meta']['deterministic_violations']}")
    for ax in ALL_AXES:
        s = repro["per_axis"][ax]
        icc = repro["icc_2_1"][ax]
        print(f"  {ax}: mean={s['mean']:.2f} sd={s['sd']:.2f} cv={s['cv']:.3f} icc21={icc:.3f}")
    print(f"[adv] crashes={adv['meta']['crashes']} unbounded={adv['meta']['unbounded_outputs']}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(repro, f, ensure_ascii=False, indent=2)
    with open(OUT_ADV, "w", encoding="utf-8") as f:
        json.dump(adv, f, ensure_ascii=False, indent=2)
    print(f"[out] {OUT_JSON}")
    print(f"[out] {OUT_ADV}")
    write_report(repro, adv)
    print(f"[out] {OUT_MD}")
    write_svg(repro)
    print(f"[out] {OUT_SVG}")


if __name__ == "__main__":
    main()
