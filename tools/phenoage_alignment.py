"""phenoage_alignment.py — H 轴自造代理 vs 文献 PhenoAge 时钟的对标装置（S1-3）
================================================================================
目的：把 HealthLens 的 H 轴/生物学年龄自造扣分表（8 项：glucose/hba1c/hs_crp/
waist/hdl/tg/sbp/bmi）与已发表的 PhenoAge 时钟（Liu 2018，9 项 + 实岁，SI 单位）
放在同一批合成画像上对照，输出两把「尺子」的年龄偏移相关性。

诚实边界（写死在输出里，防误读）：
  1. 本装置跑的是**合成画像**（同一潜变量驱动两套标志物，公式/噪声/标志物集不同），
     验证的是「装置可跑、方向一致」，**不是真实队列校准**；
  2. 两把尺子共享的原始输入只有 glucose 与 CRP——相关性度量的是仪器间一致性，
     不能推断 HealthLens 代理的人体效度；
  3. 真实校准需公开队列（如 NHANES）本地重跑，属后续工作，本装置不冒充。

输出：
  - data/phenoage_alignment.json          逐画像明细 + 汇总（可复现）
  - data/PHENOAGE_ALIGNMENT_REPORT.md     人类可读报告
  - data/phenoage_alignment_scatter.svg   散点图
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "core"))

from bioage_engine import BioAgeEngine  # noqa: E402
from phenoage import phenoage  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_JSON = os.path.join(ROOT, "data", "phenoage_alignment.json")
OUT_MD = os.path.join(ROOT, "data", "PHENOAGE_ALIGNMENT_REPORT.md")
OUT_SVG = os.path.join(ROOT, "data", "phenoage_alignment_scatter.svg")

N_PROFILES = 200
SEED = 20261013


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def gen_profile(rng: random.Random) -> dict:
    """一份合成画像：age + 共享潜变量 z 驱动两套标志物（文档化均值漂移 + 噪声）。"""
    age = rng.randint(20, 80)
    z = rng.gauss(0, 1)  # 共享的「老化负荷」潜变量
    # —— PhenoAge 9 项（SI）——
    pa_markers = {
        "albumin_g_l": _clamp(45 - 0.04 * age - 1.2 * z + rng.gauss(0, 1.5), 35, 52),
        "creatinine_umol_l": _clamp(70 + 0.5 * age + 8 * z + rng.gauss(0, 10), 50, 160),
        "glucose_mmol_l": _clamp(4.6 + 0.02 * age + 0.55 * z + rng.gauss(0, 0.5), 3.8, 12),
        "crp_mg_l": _clamp(math.exp(0.3 + 0.02 * age + 0.35 * z + rng.gauss(0, 0.6)), 0.1, 20),
        "lymph_pct": _clamp(34 - 0.05 * age - 1.5 * z + rng.gauss(0, 3), 10, 50),
        "mcv_fl": _clamp(89 + 0.05 * age + 0.8 * z + rng.gauss(0, 2), 80, 102),
        "rdw_pct": _clamp(12.5 + 0.03 * age + 0.5 * z + rng.gauss(0, 0.6), 11, 20),
        "alp_u_l": _clamp(65 + 0.25 * age + 6 * z + rng.gauss(0, 12), 35, 160),
        "wbc_1e9_l": _clamp(6.2 + 0.01 * age + 0.5 * z + rng.gauss(0, 1.0), 3.5, 12),
    }
    # —— HealthLens bioage 8 项（共享 glucose / hs_crp，其余独立采样）——
    hl_markers = {
        "glucose": pa_markers["glucose_mmol_l"],
        "hba1c": _clamp(4.8 + 0.015 * age + 0.25 * z + rng.gauss(0, 0.25), 4.2, 9.5),
        "hs_crp": pa_markers["crp_mg_l"],
        "waist_cm": _clamp(78 + 0.15 * age + 4 * z + rng.gauss(0, 5), 60, 130),
        "hdl": _clamp(1.6 - 0.004 * age - 0.12 * z + rng.gauss(0, 0.15), 0.6, 2.5),
        "triglycerides": _clamp(1.1 + 0.012 * age + 0.25 * z + rng.gauss(0, 0.3), 0.4, 6),
        "sbp": _clamp(115 + 0.35 * age + 6 * z + rng.gauss(0, 8), 95, 190),
        "bmi": _clamp(22 + 0.05 * age + 1.2 * z + rng.gauss(0, 1.5), 16, 42),
    }
    return {"age": age, "z": round(z, 4), "pa_markers": pa_markers, "hl_markers": hl_markers}


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else float("nan")


def _ranks(vs: list[float]) -> list[float]:
    order = sorted(range(len(vs)), key=lambda i: vs[i])
    ranks = [0.0] * len(vs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(_ranks(xs), _ranks(ys))


def render_svg(rows: list[dict], out_path: str, r_pearson: float) -> None:
    """浅色主题散点：x=PhenoAge delta，y=HealthLens bioage delta。"""
    W, H = 680, 460
    ml, mr, mt, mb = 64, 24, 30, 52
    pw, ph = W - ml - mr, H - mt - mb
    all_v = [r["pa_delta"] for r in rows] + [r["hl_delta"] for r in rows]
    lo, hi = min(all_v), max(all_v)
    pad = (hi - lo) * 0.08 or 1.0
    lo, hi = lo - pad, hi + pad

    def X(v: float) -> float:
        return ml + (v - lo) / (hi - lo) * pw

    def Y(v: float) -> float:
        return mt + ph - (v - lo) / (hi - lo) * ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="system-ui, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<text x="{W/2}" y="20" text-anchor="middle" font-size="14" font-weight="600" fill="#1f2937">'
        f'H 轴代理 vs PhenoAge 年龄偏移（合成画像 n={len(rows)}，Pearson r={r_pearson:.2f}）</text>',
    ]
    # 网格与坐标
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        parts.append(f'<line x1="{X(v):.1f}" y1="{mt}" x2="{X(v):.1f}" y2="{mt+ph}" stroke="#e5e7eb"/>')
        parts.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{ml+pw}" y2="{Y(v):.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{X(v):.1f}" y="{mt+ph+18}" text-anchor="middle" font-size="11" fill="#6b7280">{v:.0f}</text>')
        parts.append(f'<text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end" font-size="11" fill="#6b7280">{v:.0f}</text>')
    # 零线与 y=x 参考
    if lo < 0 < hi:
        parts.append(f'<line x1="{X(0):.1f}" y1="{mt}" x2="{X(0):.1f}" y2="{mt+ph}" stroke="#9ca3af" stroke-dasharray="4 3"/>')
        parts.append(f'<line x1="{ml}" y1="{Y(0):.1f}" x2="{ml+pw}" y2="{Y(0):.1f}" stroke="#9ca3af" stroke-dasharray="4 3"/>')
    parts.append(f'<line x1="{X(lo):.1f}" y1="{Y(lo):.1f}" x2="{X(hi):.1f}" y2="{Y(hi):.1f}" stroke="#f59e0b" stroke-dasharray="6 4"/>')
    for r in rows:
        parts.append(
            f'<circle cx="{X(r["pa_delta"]):.1f}" cy="{Y(r["hl_delta"]):.1f}" r="3.2" '
            f'fill="#2563eb" fill-opacity="0.55" stroke="#1e40af" stroke-width="0.5"/>'
        )
    parts.append(f'<text x="{ml+pw/2}" y="{H-10}" text-anchor="middle" font-size="12" fill="#374151">PhenoAge 偏移（岁）</text>')
    parts.append(f'<text x="14" y="{mt+ph/2}" text-anchor="middle" font-size="12" fill="#374151" '
                 f'transform="rotate(-90 14 {mt+ph/2})">HealthLens 生物学年龄偏移（岁）</text>')
    parts.append(f'<text x="{ml+pw-6}" y="{mt+14}" text-anchor="end" font-size="10" fill="#9ca3af">'
                 f'合成数据·装置验证·非真实队列校准</text>')
    parts.append('</svg>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main() -> None:
    rng = random.Random(SEED)
    engine = BioAgeEngine()
    rows = []
    for i in range(N_PROFILES):
        p = gen_profile(rng)
        pa = phenoage(chronological_age=p["age"], **p["pa_markers"])
        ba = engine.assess(
            p["age"], is_male=True,
            glucose=p["hl_markers"]["glucose"], hba1c=p["hl_markers"]["hba1c"],
            hs_crp=p["hl_markers"]["hs_crp"], waist_cm=p["hl_markers"]["waist_cm"],
            hdl=p["hl_markers"]["hdl"], triglycerides=p["hl_markers"]["triglycerides"],
            sbp=p["hl_markers"]["sbp"], bmi=p["hl_markers"]["bmi"],
        )
        rows.append({
            "pid": f"SYN-{i:03d}", "age": p["age"], "z": p["z"],
            "pa_phenoage": pa.phenoage, "pa_delta": pa.delta,
            "hl_bio_age": ba.bio_age, "hl_delta": ba.delta,
        })

    ok = [r for r in rows if r["pa_delta"] is not None]
    xs = [r["pa_delta"] for r in ok]
    ys = [r["hl_delta"] for r in ok]
    r_p = pearson(xs, ys)
    r_s = spearman(xs, ys)
    pa_accel = sum(1 for r in ok if r["pa_delta"] > 3)
    hl_accel = sum(1 for r in ok if r["hl_delta"] > 3)
    both = sum(1 for r in ok if r["pa_delta"] > 3 and r["hl_delta"] > 3)

    summary = {
        "n_profiles": len(rows), "n_computable": len(ok),
        "pearson_r": round(r_p, 3), "spearman_rho": round(r_s, 3),
        "mean_pa_delta": round(sum(xs) / len(xs), 2),
        "mean_hl_delta": round(sum(ys) / len(ys), 2),
        "pa_accel_gt3": pa_accel, "hl_accel_gt3": hl_accel, "both_accel": both,
        "shared_inputs": ["glucose", "crp"],
        "disclaimer": ("合成画像装置验证：同一潜变量驱动两套不同标志物集/公式/噪声；"
                       "共享原始输入仅 glucose 与 CRP；真实队列校准（如 NHANES）为后续工作"),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)

    render_svg(ok, OUT_SVG, r_p)

    md = [
        "# H 轴自造代理 vs PhenoAge 对标报告（S1-3，2026-10-13）",
        "",
        "> **合成画像装置验证**，不是真实队列校准。两把尺子共享的原始输入只有 "
        "glucose 与 CRP；相关性度量的是**仪器间一致性**，不能推断 HealthLens "
        "代理的人体效度。真实校准需公开队列本地重跑（后续工作）。",
        "",
        "## 口径",
        "- x = PhenoAge 偏移 = PhenoAge − 实岁（Liu 2018 公开公式，SI 单位，"
        "公式订正 DOI 10.1371/journal.pmed.1002760）",
        "- y = HealthLens 生物学年龄偏移 = BioAgeEngine.assess().delta"
        "（8 项自造扣分表：glucose/hba1c/hs_crp/waist/hdl/tg/sbp/bmi）",
        f"- 合成画像：n={len(rows)}（seed={SEED}），年龄 20–80，同一潜变量 z 驱动两套标志物",
        "",
        "## 结果",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 可计算画像 | {len(ok)}/{len(rows)} |",
        f"| **Pearson r** | **{r_p:.3f}** |",
        f"| Spearman ρ | {r_s:.3f} |",
        f"| PhenoAge 平均偏移 | {summary['mean_pa_delta']:+.2f} 岁 |",
        f"| HealthLens 平均偏移 | {summary['mean_hl_delta']:+.2f} 岁 |",
        f"| 偏移>3 岁（加速） | PhenoAge {pa_accel} / HealthLens {hl_accel} / 双标 {both} |",
        "",
        "## 解读边界（诚实声明）",
        "1. r/ρ 显著不为零且为正 ⇒ 两把尺子在合成数据上**方向一致**，装置可跑、公式无误；",
        "2. 共享输入仅 glucose+CRP ⇒ 相关性**不能**作为 H 轴人体效度证据；",
        "3. 论文可写的措辞：「we implemented the published PhenoAge (Liu 2018) as a "
        "benchmark harness and established an alignment装置 on synthetic profiles; "
        "calibration against a reference cohort remains future work」——"
        "**不可**写成「aligned with PhenoAge on real data」。",
        "",
        "*逐画像明细：`data/phenoage_alignment.json`；散点：`data/phenoage_alignment_scatter.svg`。*",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
