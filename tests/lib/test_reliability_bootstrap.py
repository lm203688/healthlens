"""C2 信度量化 bootstrap 测试

10-17 科学先进性评估报告 S6：「零信度证据——工具开发论文的必填项」。
本测试守住两个不变量：
1. 脚本可运行且产出 JSON
2. 八轴 ICC 与 Kappa 均在合理范围内（excellent/good 级）
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def test_reliability_bootstrap_script_exists():
    path = REPO_ROOT / "tools" / "reliability_bootstrap.py"
    assert path.exists(), f"tools/reliability_bootstrap.py 不存在"


def test_reliability_bootstrap_produces_json():
    """脚本运行必须产出 engine_reliability_metrics.json 且包含八轴结果。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap, ALL_AXES

    # 用较少迭代次数（50）快速验证脚本可运行
    results = run_reliability_bootstrap(n_iterations=50, perturbation_pct=0.05, seed=20261017)

    assert len(results) == 8, f"应产出 8 轴结果，实际 {len(results)}"
    axes = {r.axis for r in results}
    assert axes == set("ABCDEFGH"), f"轴集合应为 A-H，实际 {axes}"

    for r in results:
        assert 0.0 <= r.icc_2_1 <= 1.0, f"轴 {r.axis} ICC={r.icc_2_1} 越界"
        assert -1.0 <= r.weighted_kappa <= 1.0, f"轴 {r.axis} Kappa={r.weighted_kappa} 越界"
        assert 0.0 <= r.baseline_mean <= 100.0, f"轴 {r.axis} 基线均值越界"
        assert r.reliability_grade in {"excellent", "good", "moderate", "insufficient"}, (
            f"轴 {r.axis} 信度分级无效: {r.reliability_grade}"
        )


def test_reliability_bootstrap_seed_determinism():
    """相同种子必须产出相同结果（论文复现承诺）。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap

    r1 = run_reliability_bootstrap(n_iterations=100, seed=42)
    r2 = run_reliability_bootstrap(n_iterations=100, seed=42)

    for a, b in zip(r1, r2):
        assert a.axis == b.axis
        assert a.icc_2_1 == b.icc_2_1, f"轴 {a.axis} ICC 随种子漂移"
        assert a.weighted_kappa == b.weighted_kappa, f"轴 {a.axis} Kappa 随种子漂移"


def test_reliability_bootstrap_high_icc_for_threshold_stable_axes():
    """F 轴（hs-CRP/IL-6 硬阈值）必须 ICC=1.0（扰动不跨越阈值）。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap

    results = run_reliability_bootstrap(n_iterations=200, seed=20261017)
    f_axis = next(r for r in results if r.axis == "F")
    assert f_axis.icc_2_1 >= 0.999, (
        f"F 轴（hs-CRP/IL-6 硬阈值，远离边界时扰动不变）ICC={f_axis.icc_2_1}，"
        "应接近 1.0——固定阈值打分器在阈值稳定区应完全一致"
    )


def test_reliability_bootstrap_all_axes_passes_min_reliability():
    """八轴至少应达到 moderate 级信度（ICC ≥ 0.50），工具开发论文底线。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap

    results = run_reliability_bootstrap(n_iterations=500, seed=20261017)

    below_threshold = [r for r in results if r.icc_2_1 < 0.50]
    assert not below_threshold, (
        f"以下轴信度不足（ICC < 0.50）：{[(r.axis, r.icc_2_1) for r in below_threshold]}。\n"
        "工具开发论文不得发表信度不足的轴。"
    )


def test_reliability_bootstrap_kappa_reasonable():
    """Weighted Kappa 应 ≥ 0.85（优秀一致性），因为 ±5% 扰动多在同一分档内。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap

    results = run_reliability_bootstrap(n_iterations=300, seed=20261017)

    below_kappa = [r for r in results if r.weighted_kappa < 0.85]
    assert not below_kappa, (
        f"以下轴 Kappa 不足（< 0.85）：{[(r.axis, r.weighted_kappa) for r in below_kappa]}。"
    )


def test_reliability_bootstrap_score_range_bounded():
    """所有 bootstrap 分数必须在 [0, 100] 内（八轴定义域）。"""
    from tools.reliability_bootstrap import run_reliability_bootstrap

    results = run_reliability_bootstrap(n_iterations=200, seed=20261017)

    for r in results:
        lo, hi = r.score_range
        assert lo >= 0.0, f"轴 {r.axis} 最低分 {lo} 越界"
        assert hi <= 100.0, f"轴 {r.axis} 最高分 {hi} 越界"


def test_reliability_bootstrap_reliability_metrics_file_written():
    """main() 必须写出 engine_reliability_metrics.json 且 JSON 结构完整。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "tools/reliability_bootstrap.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"脚本执行失败: {result.stderr}"

    out_path = REPO_ROOT / "engine_reliability_metrics.json"
    assert out_path.exists(), "engine_reliability_metrics.json 未生成"

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["method"] == "input_perturbation_bootstrap"
    assert data["parameters"]["n_iterations"] == 1000
    assert data["parameters"]["perturbation_pct"] == 0.05
    assert len(data["results"]) == 8
    for r in data["results"]:
        assert r["axis"] in set("ABCDEFGH")
        assert 0.0 <= r["icc_2_1"] <= 1.0
        assert r["reliability_grade"] in {"excellent", "good", "moderate", "insufficient"}
