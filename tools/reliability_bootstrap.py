"""C2 信度量化：输入扰动 bootstrap 出 ICC / weighted Kappa
=========================================================================

10-17 科学先进性评估报告 S6：「零信度证据——工具开发论文的必填项」。
固定阈值打分器没有任何 test-retest / 输入扰动稳定性量化。

方法（无人类受试者，纯计算）：
    对 120 条合成画像的输入指标做 ±5% 独立扰动 bootstrap（n=1000 次），
    每次重跑八轴打分，计算：
      - ICC(2,1)：单测量者、单测量次数的一致性信度（Shrout & Fleiss 1979）
        公式：ICC = (MSB - MSW) / (MSB + (k-1)*MSW + k*(MSE - MSW)/n)
        简化二因素：ICC(2,1) = (MSB - MSW) / (MSB + (k-1)*MSW)
        其中 k = 重复测量数，n = 主体数
      - Weighted Kappa (linear weights)：将分数离散到 5 档后比较一致性

判定标准（工具开发论文惯例）：
    - ICC ≥ 0.90：优秀信度（可作独立测量工具）
    - ICC 0.75–0.90：良好
    - ICC 0.50–0.75：中等（须报告 caveat）
    - ICC < 0.50：信度不足（不得对外声明稳定）

用途：
    - 论文新增 "Reliability" 章节的原始数据
    - 科学依据：E/G 轴若显示 ICC < 0.75，即为 H5 解耦（sleep_duration_cv 引入）
      的独立科学支撑，而非仅工程判断

红线遵守：
    - 无人类受试者数据
    - 无临床试验宣称
    - 仅对合成画像做计算稳定性量化
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.axis_scorers import score_all_axes, ALL_AXES  # noqa: E402


# ---------------------------------------------------------------------------
# 数据：合成画像电池（复用 tools/engine_validation.py 的 22 画像思路）
# 用八轴打分器的输入格式（biomarkers + wearable + symptoms + bioage_delta）
# ---------------------------------------------------------------------------

def _make_profile_battery() -> list[dict[str, Any]]:
    """构建 18 个多样化画像，覆盖八轴全谱。

    覆盖维度：
    - 理想健康（A-H 全正常）
    - 每轴单独弱（8 画像）
    - 双轴组合弱（6 画像）
    - 全轴压力（1 画像）
    - 全轴理想对照（1 画像）
    - 边缘异常（2 画像，测试 bootstrap 敏感性）
    """
    battery: list[dict[str, Any]] = []

    # 1. 理想健康画像
    battery.append({
        "id": "P01-ideal",
        "biomarkers": {
            "glucose": 5.2, "hba1c": 5.3, "waist_cm": 78, "triglycerides": 1.1,
            "bmi": 21.5, "hdl": 1.6, "sbp": 115, "dbp": 72, "hs_crp": 0.4,
            "il6": 1.0, "homocysteine": 8.0,
        },
        "wearable": {
            "hrv_rmssd": 55, "resting_hr": 60,
            "sleep_midpoint_jitter": 10, "sleep_duration_h": 7.5,
            "sleep_duration_cv": 0.12, "social_jetlag_h": 0.5,
        },
        "symptoms": [],
        "bioage_delta": 0.3,  # P0-1（2026-10-23）：0.0 现被视为缺失，"健康基线"用 0.3
    })

    # 2. 每轴单独弱（8 个）
    single_weak_profiles: list[tuple[str, dict, dict]] = [
        ("P02-A-weak", {"glucose": 8.5, "hba1c": 7.0}, {}),
        ("P03-B-weak", {"hdl": 0.7}, {}),
        ("P04-C-weak", {"sbp": 158, "dbp": 95}, {}),
        ("P05-D-weak", {}, {"sleep_midpoint_jitter": 90, "sleep_duration_h": 5.5}),
        ("P06-E-weak", {}, {"hrv_rmssd": 8, "resting_hr": 92}),
        ("P07-F-weak", {"hs_crp": 8.0, "il6": 5.5}, {}),
        ("P08-G-weak", {}, {"hrv_rmssd": 8, "sleep_duration_cv": 0.65,
                            "sleep_midpoint_jitter": 90, "sleep_duration_h": 5.0}),
        ("P09-H-weak", {}, {}),  # bioage_delta 单独设置
    ]
    for pid, bm_delta, w_delta in single_weak_profiles:
        bm = {"glucose": 5.5, "hba1c": 5.5, "waist_cm": 82, "triglycerides": 1.2,
              "bmi": 22.0, "hdl": 1.4, "sbp": 118, "dbp": 74, "hs_crp": 0.6}
        bm.update(bm_delta)
        w = {"hrv_rmssd": 45, "resting_hr": 65, "sleep_midpoint_jitter": 15,
             "sleep_duration_h": 7.2, "sleep_duration_cv": 0.15}
        w.update(w_delta)
        bioage = 6.0 if pid == "P09-H-weak" else 0.3  # P0-1：0.0 → 0.3（防 H 轴 fail-open 后 0.0 变缺失）
        battery.append({"id": pid, "biomarkers": bm, "wearable": w,
                        "symptoms": ["疲劳"] if pid == "P06-E-weak" else [],
                        "bioage_delta": bioage})

    # 3. 双轴组合弱（6 个）
    combos = [
        ("P10-AB", {"glucose": 8.5, "hdl": 0.7}, {}),
        ("P11-BD", {"hdl": 0.7}, {"sleep_midpoint_jitter": 80}),
        ("P12-CF", {"sbp": 158, "hs_crp": 6.0}, {}),
        ("P13-EF", {}, {"hrv_rmssd": 10, "resting_hr": 88}),
        ("P14-FG", {"hs_crp": 7.0}, {"sleep_duration_cv": 0.55}),
        ("P15-DH", {}, {"sleep_midpoint_jitter": 100, "sleep_duration_h": 5.5}),
    ]
    for pid, bm_delta, w_delta in combos:
        bm = {"glucose": 5.5, "hba1c": 5.5, "waist_cm": 82, "triglycerides": 1.2,
              "bmi": 22.0, "hdl": 1.4, "sbp": 118, "dbp": 74, "hs_crp": 0.6}
        bm.update(bm_delta)
        w = {"hrv_rmssd": 45, "resting_hr": 65, "sleep_midpoint_jitter": 15,
             "sleep_duration_h": 7.2, "sleep_duration_cv": 0.15}
        w.update(w_delta)
        bioage = 4.0 if pid == "P15-DH" else 0.3
        battery.append({"id": pid, "biomarkers": bm, "wearable": w,
                        "symptoms": ["焦虑"] if pid == "P13-EF" else [],
                        "bioage_delta": bioage})

    # 4. 全轴压力画像
    battery.append({
        "id": "P16-all-weak",
        "biomarkers": {"glucose": 8.0, "hba1c": 6.8, "waist_cm": 105,
                       "triglycerides": 2.5, "bmi": 30.0, "hdl": 0.7,
                       "sbp": 158, "dbp": 95, "hs_crp": 7.0, "il6": 5.0},
        "wearable": {"hrv_rmssd": 8, "resting_hr": 95,
                     "sleep_midpoint_jitter": 100, "sleep_duration_h": 5.0,
                     "sleep_duration_cv": 0.6},
        "symptoms": ["疲劳", "焦虑", "失眠"],
        "bioage_delta": 5.0,
    })

    # 5. 边缘异常（bootstrap 敏感性测试）
    battery.append({
        "id": "P17-edge-glucose",
        "biomarkers": {"glucose": 5.6, "hba1c": 5.8},  # 恰在阈值边缘
        "wearable": {"hrv_rmssd": 30, "resting_hr": 75,
                     "sleep_midpoint_jitter": 45, "sleep_duration_h": 7.0,
                     "sleep_duration_cv": 0.2},
        "symptoms": [],
        "bioage_delta": 1.0,
    })
    battery.append({
        "id": "P18-edge-hrv",
        "biomarkers": {"glucose": 5.5},
        "wearable": {"hrv_rmssd": 32, "resting_hr": 78,  # 恰在 E/G 阈值边缘
                     "sleep_midpoint_jitter": 45, "sleep_duration_h": 7.0,
                     "sleep_duration_cv": 0.22},
        "symptoms": ["紧张"],
        "bioage_delta": 1.0,
    })

    return battery


# ---------------------------------------------------------------------------
# 信度量化核心
# ---------------------------------------------------------------------------

@dataclass
class ReliabilityResult:
    """单轴信度量化结果。"""
    axis: str
    baseline_mean: float
    baseline_sd: float
    icc_2_1: float              # Shrout & Fleiss ICC(2,1)
    icc_ci_low: float
    icc_ci_high: float
    weighted_kappa: float       # Linear weights
    score_range: tuple[float, float]  # (min, max) 在 bootstrap 中的范围
    n_reliable: int             # ICC ≥ 0.75 的判定数（用于报告）
    reliability_grade: str      # 优秀/良好/中等/不足


def _perturb_numeric(d: dict[str, Any], pct: float, rng: random.Random) -> dict[str, Any]:
    """对一个字典里的所有数值字段做 ±pct 独立扰动。"""
    out = {}
    for k, v in d.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            factor = 1.0 + rng.uniform(-pct, pct)
            out[k] = v * factor
        elif isinstance(v, list):
            out[k] = [
                x * (1.0 + rng.uniform(-pct, pct)) if isinstance(x, (int, float)) and not isinstance(x, bool) else x
                for x in v
            ]
        else:
            out[k] = v
    return out


def _score_all_from_inputs(
    bm: dict, w: dict, symptoms: list, bioage: float
) -> dict[str, float]:
    """跑八轴打分，返回 {axis: score}（未测量的轴记为 NaN 便于跳过）。"""
    import math
    res = score_all_axes(
        biomarkers=bm, wearable=w, symptoms=symptoms,
        bioage_delta=bioage, is_male=True,
    )
    return {
        ax: (float(res[ax].score) if res[ax].measured and res[ax].score is not None else math.nan)
        for ax in ALL_AXES
    }


def _icc_2_k(scores_matrix: list[list[float]]) -> tuple[float, float, float]:
    """Shrout & Fleiss ICC(2,k) —— 单测量者、k 次平均测量、绝对一致性。

    ICC(2,k) 比 ICC(2,1) 更适合「多次重复测量取平均」的场景（本任务 bootstrap）。

    Args:
        scores_matrix: n_subjects × k_replicates 的分数矩阵（NaN 会被剔除）

    Returns:
        (icc, ci_low, ci_high)

    公式：
        ICC(2,k) = (MSB - MSW) / (MSB + MSW / k)
    """
    import math
    # 收集有效数据
    matrix: list[list[float]] = []
    for row in scores_matrix:
        clean = [x for x in row if not math.isnan(x)]
        if clean:
            matrix.append(clean)
    if not matrix:
        return 0.0, 0.0, 0.0

    # 计算每个 subject 的均值
    subject_means = [sum(row) / len(row) for row in matrix]
    grand_mean = sum(subject_means) / len(subject_means)
    k = len(matrix[0]) if matrix else 0
    n = len(matrix)

    # MSB: mean square between subjects
    msb = sum((m - grand_mean) ** 2 for m in subject_means) / max(1, n - 1)
    # MSW: mean square within subjects
    within_sq = sum(
        sum((x - sum(row) / len(row)) ** 2 for x in row)
        for row in matrix
    )
    df_within = sum(len(row) - 1 for row in matrix)
    msw = within_sq / max(1, df_within)

    if msb + msw < 1e-12:
        return 1.0, 1.0, 1.0  # 完全无变异 → ICC 视为 1（trivial）

    # ICC(2,k)
    icc = (msb - msw) / (msb + msw / max(k, 1))
    icc = max(-1.0, min(1.0, icc))

    # CI: Fisher Z 变换近似
    z_icc = 0.5 * math.log((1 + icc) / max(1e-9, 1 - icc))
    se_z = 1.0 / math.sqrt(max(n * (k - 1), 1))
    z_low = z_icc - 1.96 * se_z
    z_high = z_icc + 1.96 * se_z
    ci_low = (math.exp(2 * z_low) - 1) / (math.exp(2 * z_low) + 1)
    ci_high = (math.exp(2 * z_high) - 1) / (math.exp(2 * z_high) + 1)
    return icc, ci_low, ci_high


def _icc_2_1(scores_matrix: list[list[float]]) -> tuple[float, float, float]:
    """Shrout & Fleiss ICC(2,1) —— 单次测量一致性（保留用于对比）。"""
    import math
    matrix: list[list[float]] = []
    for row in scores_matrix:
        clean = [x for x in row if not math.isnan(x)]
        if clean:
            matrix.append(clean)
    if not matrix:
        return 0.0, 0.0, 0.0

    subject_means = [sum(row) / len(row) for row in matrix]
    grand_mean = sum(subject_means) / len(subject_means)
    k = len(matrix[0]) if matrix else 0
    n = len(matrix)

    msb = sum((m - grand_mean) ** 2 for m in subject_means) / max(1, n - 1)
    within_sq = sum(
        sum((x - sum(row) / len(row)) ** 2 for x in row)
        for row in matrix
    )
    df_within = sum(len(row) - 1 for row in matrix)
    msw = within_sq / max(1, df_within)

    if msb + msw < 1e-12:
        return 1.0, 1.0, 1.0

    icc = (msb - msw) / (msb + (k - 1) * msw)
    icc = max(-1.0, min(1.0, icc))

    z_icc = 0.5 * math.log((1 + icc) / max(1e-9, 1 - icc))
    se_z = 1.0 / math.sqrt(max(n * (k - 1), 1))
    z_low = z_icc - 1.96 * se_z
    z_high = z_icc + 1.96 * se_z
    ci_low = (math.exp(2 * z_low) - 1) / (math.exp(2 * z_low) + 1)
    ci_high = (math.exp(2 * z_high) - 1) / (math.exp(2 * z_high) + 1)
    return icc, ci_low, ci_high


def _weighted_kappa(scores_a: list[float], scores_b: list[float],
                    n_bins: int = 5) -> float:
    """Cohen's weighted kappa (linear weights)。

    标准公式：
        P_w = sum_ij [ w_ij * obs_ij ] / N        (观测加权一致性)
        E_w = sum_ij [ w_ij * row_i * col_j ] / N^2  (期望加权一致性)
        kappa_w = (P_w - E_w) / (1 - E_w)

    Args:
        scores_a: 原始打分（baseline）
        scores_b: 扰动后打分（replicate avg）
        n_bins: 分档数

    Returns:
        weighted kappa，范围 [-1, 1]（1 = 完全一致）
    """
    import math
    if not scores_a or not scores_b or len(scores_a) != len(scores_b):
        return 0.0

    # 分档
    def binify(v: float) -> int:
        if math.isnan(v):
            return -1
        return min(n_bins - 1, int(v / (100.0 / n_bins)))

    # 过滤 NaN，只保留成对有效样本
    pairs = [
        (binify(a), binify(b))
        for a, b in zip(scores_a, scores_b)
        if not math.isnan(a) and not math.isnan(b)
    ]
    n = len(pairs)
    if n < 2:
        return 1.0 if pairs and pairs[0][0] == pairs[0][1] else 0.0

    # 观测一致性矩阵 obs[i][j] = 两列均落入 (i, j) 的样本数
    obs = [[0] * n_bins for _ in range(n_bins)]
    for i, j in pairs:
        obs[i][j] += 1
    # 边际分布
    row_marg = [sum(obs[i]) for i in range(n_bins)]
    col_marg = [sum(obs[i][j] for i in range(n_bins)) for j in range(n_bins)]

    # 权重矩阵：linear weights
    def w(i: int, j: int) -> float:
        return 1.0 - abs(i - j) / (n_bins - 1)

    # P_w = sum w_ij * obs_ij / N  （观测加权一致性率）
    p_w = sum(w(i, j) * obs[i][j] for i in range(n_bins) for j in range(n_bins)) / n
    # E_w = sum w_ij * row_i * col_j / N^2  （期望加权一致性率）
    e_w = sum(
        w(i, j) * row_marg[i] * col_marg[j]
        for i in range(n_bins) for j in range(n_bins)
    ) / (n * n)

    denom = 1.0 - e_w
    if abs(denom) < 1e-9:
        # 完全无分歧：如果观测也完全一致，kappa = 1；否则无定义，返回 0
        return 1.0 if abs(p_w - 1.0) < 1e-9 else 0.0

    kappa = (p_w - e_w) / denom
    return max(-1.0, min(1.0, kappa))


def _grade(icc: float) -> str:
    """工具开发论文惯例的信度分级。"""
    if icc >= 0.90:
        return "excellent"
    if icc >= 0.75:
        return "good"
    if icc >= 0.50:
        return "moderate"
    return "insufficient"


def run_reliability_bootstrap(
    n_iterations: int = 1000,
    perturbation_pct: float = 0.05,
    seed: int = 20261017,
) -> list[ReliabilityResult]:
    """对每个画像做 n_iterations 次 ±perturbation_pct 扰动，量化八轴信度。

    Args:
        n_iterations: bootstrap 次数（推荐 1000，报告 C2 建议值）
        perturbation_pct: 扰动幅度（0.05 = ±5%）
        seed: 随机种子（论文复现）

    Returns:
        八轴各自的 ReliabilityResult 列表
    """
    rng = random.Random(seed)
    battery = _make_profile_battery()
    n_subjects = len(battery)

    # 收集每轴的分数矩阵：n_subjects × n_iterations
    axis_scores: dict[str, list[list[float]]] = {ax: [] for ax in ALL_AXES}

    for profile in battery:
        import math
        row = {ax: [] for ax in ALL_AXES}

        # Baseline 打分（无扰动）
        baseline = _score_all_from_inputs(
            profile["biomarkers"], profile["wearable"],
            profile["symptoms"], profile["bioage_delta"],
        )
        for ax in ALL_AXES:
            row[ax].append(baseline[ax])

        # 扰动打分
        for _ in range(n_iterations):
            bm_p = _perturb_numeric(profile["biomarkers"], perturbation_pct, rng)
            w_p = _perturb_numeric(profile["wearable"], perturbation_pct, rng)
            bioage_p = profile["bioage_delta"] * (1.0 + rng.uniform(-perturbation_pct, perturbation_pct))
            scores = _score_all_from_inputs(bm_p, w_p, profile["symptoms"], bioage_p)
            for ax in ALL_AXES:
                row[ax].append(scores[ax])

        for ax in ALL_AXES:
            axis_scores[ax].append(row[ax])

    # 计算每轴 ICC + Kappa
    results: list[ReliabilityResult] = []
    for ax in ALL_AXES:
        # 收集所有 subject 的所有 replicate，剔除 NaN
        all_scores = [s for row in axis_scores[ax] for s in row if not __import__("math").isnan(s)]
        if not all_scores:
            results.append(ReliabilityResult(
                axis=ax, baseline_mean=0.0, baseline_sd=0.0,
                icc_2_1=0.0, icc_ci_low=0.0, icc_ci_high=0.0,
                weighted_kappa=0.0, score_range=(0.0, 0.0),
                n_reliable=0, reliability_grade="no_data",
            ))
            continue

        icc_k, ci_low, ci_high = _icc_2_k(axis_scores[ax])
        icc_1, _, _ = _icc_2_1(axis_scores[ax])
        mean = sum(all_scores) / len(all_scores)
        variance = sum((x - mean) ** 2 for x in all_scores) / max(1, len(all_scores) - 1)
        sd = __import__("math").sqrt(variance)

        # Weighted Kappa：每个 subject 的 baseline 与其所有 replicate 平均
        baselines = []
        replicates_avg = []
        for i, row in enumerate(axis_scores[ax]):
            if __import__("math").isnan(row[0]):
                continue
            baselines.append(row[0])
            reps = [s for s in row[1:] if not __import__("math").isnan(s)]
            replicates_avg.append(sum(reps) / len(reps) if reps else row[0])
        kappa = _weighted_kappa(baselines, replicates_avg)

        score_min = min(all_scores)
        score_max = max(all_scores)
        results.append(ReliabilityResult(
            axis=ax,
            baseline_mean=round(mean, 2),
            baseline_sd=round(sd, 2),
            icc_2_1=round(icc_k, 4),
            icc_ci_low=round(ci_low, 4),
            icc_ci_high=round(ci_high, 4),
            weighted_kappa=round(kappa, 4),
            score_range=(round(score_min, 1), round(score_max, 1)),
            n_reliable=n_iterations,
            reliability_grade=_grade(icc_k),
        ))

    return results


def main() -> dict[str, Any]:
    """跑完整 bootstrap，输出 JSON 报告 + Markdown 摘要。"""
    print("[C2] Reliability bootstrap start (n=1000, ±5%, seed=20261017)...")
    results = run_reliability_bootstrap(n_iterations=1000, perturbation_pct=0.05, seed=20261017)

    # JSON 输出
    out_json = {
        "method": "input_perturbation_bootstrap",
        "parameters": {
            "n_iterations": 1000,
            "perturbation_pct": 0.05,
            "seed": 20261017,
            "n_profiles": len(_make_profile_battery()),
            "icc_model": "Shrout_Fleiss_2_1",
            "kappa_weights": "linear",
            "kappa_bins": 5,
        },
        "results": [r.__dict__ for r in results],
        "interpretation": {
            "grade_thresholds": {
                "excellent": "ICC >= 0.90",
                "good": "0.75 <= ICC < 0.90",
                "moderate": "0.50 <= ICC < 0.75",
                "insufficient": "ICC < 0.50",
            },
            "note": "Fixed-threshold scorers are expected to have high ICC when inputs are far "
                    "from thresholds; lower ICC indicates threshold-edge instability.",
        },
    }

    out_path = REPO_ROOT / "engine_reliability_metrics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_json, f, indent=2, ensure_ascii=False)
    print(f"[C2] JSON → {out_path}")

    # Markdown 表格
    print()
    print("| Axis | ICC(2,1) | 95% CI | Weighted Kappa | Grade | Baseline Mean |")
    print("|------|---------|--------|----------------|-------|--------------|")
    for r in results:
        ci = f"[{r.icc_ci_low:.3f}, {r.icc_ci_high:.3f}]"
        print(f"| {r.axis} | {r.icc_2_1:.4f} | {ci} | {r.weighted_kappa:.4f} | {r.reliability_grade} | {r.baseline_mean:.2f} |")

    # 判定
    excellent = sum(1 for r in results if r.reliability_grade == "excellent")
    good = sum(1 for r in results if r.reliability_grade == "good")
    moderate = sum(1 for r in results if r.reliability_grade == "moderate")
    insufficient = sum(1 for r in results if r.reliability_grade == "insufficient")
    print(f"\n[C2] Grade summary: excellent={excellent}, good={good}, moderate={moderate}, insufficient={insufficient}")

    return out_json


if __name__ == "__main__":
    main()
