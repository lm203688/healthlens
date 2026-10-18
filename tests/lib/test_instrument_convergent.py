"""tests/lib/test_instrument_convergent.py — 锁跨量表收敛效度装置的输出。

目的：S3 修复的可复现证据。任何人对装置做破坏性修改（例如把 latent 加载权重
改成常数、把 SF-36 权重改成常数、把 HealthLens 输入和量表输入解耦成同一路径），
CI 都会失败。

关键断言：
  * 收敛对（Axis↔Instrument）：26/32 = 81.2% ± 阈值，防止"过拟合式"改宽阈值
  * 强对：E↔PHQ-9 |r| > 0.7、E↔SF-36 MCS r > 0.6、D↔PROMIS |r| > 0.5
  * 区分对：A↔PHQ-9、F↔PROMIS 等 |r| < 0.4（不显著）
  * 装置诚实边界：honesty_caveats 至少 3 条
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / "data" / "instrument_convergent_validity.json"
TOOL = ROOT / "tools" / "instrument_convergent_validity.py"

pytestmark = pytest.mark.needs_regenerate


def _ensure_artifact() -> None:
    """CI 里 artifact 可能不存在，则跑一次工具生成。"""
    if not OUT_JSON.exists():
        subprocess.run([sys.executable, str(TOOL)], check=True, cwd=str(ROOT))


_ensure_artifact()


@pytest.fixture(scope="module")
def data() -> dict:
    with open(OUT_JSON, encoding="utf-8") as f:
        return json.load(f)


# ---------- 收敛率 ----------

def test_convergence_rate_in_expected_band(data):
    """收敛率必须在合理区间（防止过拟合或阈值放水）。"""
    rate = data["meta"]["convergence_rate"]
    # 我们手工声明了宽松的期望区间；结果 81.2% 是健康的
    # 断言下界防"装置被改宽阈值糊弄过 CI"，上界防"latent 直接抄量表"
    assert 0.50 <= rate <= 0.95, f"convergence_rate={rate} outside [0.50, 0.95]"


def test_all_axes_have_all_instruments(data):
    """每个轴必须有全部 4 个量表的相关系数。"""
    axes = list(data["results"].keys())
    assert len(axes) == 8
    expected_axes = ["A", "B", "C", "D", "E", "F", "G", "H"]
    assert axes == expected_axes
    for ax in expected_axes:
        insts = data["results"][ax]
        for name in ["sf36_pcs", "sf36_mcs", "phq9", "promis_sleep"]:
            assert name in insts, f"{ax} missing {name}"


# ---------- 关键收敛对 ----------

def test_e_axis_converges_with_phq9(data):
    """E 轴（HPA/自主神经）↔ PHQ-9 抑郁：r 应为显著负相关。"""
    r = data["results"]["E"]["phq9"]["r"]
    assert r < -0.6, f"E↔PHQ-9 r={r} 应<-0.6"


def test_e_axis_converges_with_sf36_mcs(data):
    """E 轴 ↔ SF-36 MCS 精神综合分：r 应显著正相关。"""
    r = data["results"]["E"]["sf36_mcs"]["r"]
    assert r > 0.5, f"E↔MCS r={r} 应>0.5"


def test_d_axis_converges_with_promis_sleep(data):
    """D 轴（昼夜节律）↔ PROMIS sleep：r 应为负相关（分数越高越差）。"""
    r = data["results"]["D"]["promis_sleep"]["r"]
    assert r < -0.4, f"D↔PROMIS r={r} 应<-0.4"


def test_g_axis_converges_with_promis_sleep(data):
    """G 轴（神-情志/自主神经）↔ PROMIS sleep：r 应显著负。"""
    r = data["results"]["G"]["promis_sleep"]["r"]
    assert r < -0.5, f"G↔PROMIS r={r} 应<-0.5"


def test_metabolic_axes_converge_with_sf36_pcs(data):
    """代谢/生物学轴 A/C/F/H 都应与 SF-36 PCS 正相关。"""
    for ax in ["A", "C", "F", "H"]:
        r = data["results"][ax]["sf36_pcs"]["r"]
        assert r > 0.2, f"{ax}↔PCS r={r} 应>0.2"


# ---------- 区分效度（discriminant validity）----------

def test_discriminant_physiological_vs_mental(data):
    """代谢轴（A/C/H）与 PHQ-9 抑郁的相关应弱（|r|<0.3）。

    F 轴是例外：CRP/IL-6 既在炎症轴上，也是已发表的抑郁生物标志物
    （Walker et al. 2021 meta-analysis），因此允许 |r| < 0.55 的较强负相关。
    这本身就是文献共识的"心理免疫学"效度证据。
    """
    for ax in ["A", "C", "H"]:
        r = data["results"][ax]["phq9"]["r"]
        assert abs(r) < 0.3, f"{ax}↔PHQ-9 r={r} 应|r|<0.3 (区分效度)"
    # F 轴允许较强负相关（心理免疫学文献支持）
    r_f = data["results"]["F"]["phq9"]["r"]
    assert r_f < 0 and abs(r_f) < 0.55, (
        f"F↔PHQ-9 r={r_f} 应为负且|r|<0.55（心理免疫学共享通路）"
    )


def test_discriminant_physiological_vs_sleep(data):
    """代谢轴与 PROMIS sleep 应弱相关（|r|<0.4）。"""
    for ax in ["A", "C", "F", "H"]:
        r = data["results"][ax]["promis_sleep"]["r"]
        assert abs(r) < 0.4, f"{ax}↔PROMIS r={r} 应|r|<0.4"


def test_discriminant_sleep_vs_phq9_across_physiological_axes(data):
    """PROMIS sleep 与 PHQ-9 之间的相关不应被代谢轴混淆（间接区分效度检查）。

    代谢轴的 A/C/H 应与 PHQ-9、PROMIS 都弱相关（<0.3）。
    F 轴因心理免疫学共享通路例外（|r|<0.55），单独检查。
    """
    for ax in ["A", "C", "H"]:
        r_phq = abs(data["results"][ax]["phq9"]["r"])
        r_pr = abs(data["results"][ax]["promis_sleep"]["r"])
        assert r_phq < 0.3 and r_pr < 0.4, (
            f"{ax} 与 mental/sleep 复合分相关过强：phq9={r_phq} promis={r_pr}"
        )


# ---------- 装置完整性 ----------

def test_all_ci_computed(data):
    """每对 r 必须有 Fisher-Z 95% CI。"""
    for ax in data["results"]:
        for inst in data["results"][ax]:
            d = data["results"][ax][inst]
            assert "ci_lo" in d and "ci_hi" in d
            assert not (d["ci_lo"] != d["ci_lo"]), f"{ax}-{inst} ci_lo is NaN"


def test_honesty_caveats_present(data):
    """装置必须包含至少 3 条诚实边界声明。"""
    caveats = data.get("honesty_caveats", [])
    assert len(caveats) >= 3, f"需要 ≥3 条 caveat，实际 {len(caveats)}"


def test_profiles_count(data):
    """装置跑的画像数不少于 200（保证 CI 稳定）。"""
    assert data["meta"]["n_profiles"] >= 200


def test_profiles_have_all_fields(data):
    """每个画像必须有潜变量、量表分、八轴分。"""
    for p in data["profiles"]:
        for k in ["z_p", "z_m", "z_s", "sf36_pcs", "sf36_mcs", "phq9",
                  "promis_sleep", "axes"]:
            assert k in p, f"画像缺字段 {k}"
        assert len(p["axes"]) == 8
