"""稳态生物学八轴打分器 (Axis Scorers) — HealthLens 科学内核 P0-1
==============================================================

把「古籍气/血/脏腑/阴阳/正邪/神/先天」公理化映射为 8 条可测量的稳态生物学轴
(A–H)，并为每条轴提供**至少一个可验证代理指标 + 透明公式**。

设计原则（与 bioage_engine 一致，守住 wellness 边界且诚实）：
- 全模块仅依赖标准库，可在「无 FastAPI 重依赖」的精简环境被 importlib 按路径加载。
- 每条轴 score 取值 0-100（高=稳态越好）；**单轴无可用数据时显式标 `measured=False`，
  绝不填 0**（填 0 等于「假装测过且最差」，会污染融合与论文结论）。
- 公式系数源自公开临床阈值（ADA / 中国心血管病风险指南 / 中国血脂异常防治指南 /
  ESC 血压/HRV 参考），是透明启发式，**非黑箱模型、非诊断**。每条结果带 `sources`
  字段说明用了哪些真实输入，便于端到端追溯。
- 任何结果不构成医疗诊断、处方或治疗建议。

八轴定义（与代码/论文统一的 A–H，已消除 I/J 论文漂移）：
  A 气化-自噬(AMPK-mTOR)      ← 血糖/HbA1c/BMI/腰围/甘油三酯
  B 气血-线粒体能量(NAD+/mtDNA)← HDL/甘油三酯/静息心率/同型半胱氨酸(可选)
  C 络脉-内皮微循环           ← 收缩压/舒张压/hs-CRP/同型半胱氨酸(可选)
  D 阴阳-昼夜节律             ← 睡眠中点抖动/睡眠时长/社会时差(需可穿戴睡眠)
  E 脏腑-神经内分泌(HPA)      ← HRV(RMSSD)/静息心率/压力症状
  F 正邪-炎症负荷             ← hs-CRP/IL-6
  G 神-情志(自主神经)         ← HRV(RMSSD)/睡眠规律性
  H 先天-肾精(表观遗传)       ← 表观遗传年龄偏移(bioage delta)/端粒(可选)
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 八轴元数据
# ---------------------------------------------------------------------------

AXIS_META: dict[str, dict] = {
    "A": {"label": "气化-自噬(AMPK-mTOR)", "concept": "气/气化", "proxy": "血糖代谢稳态"},
    "B": {"label": "气血-线粒体能量(NAD+/mtDNA)", "concept": "气血", "proxy": "线粒体能量代谢"},
    "C": {"label": "络脉-内皮微循环", "concept": "络脉", "proxy": "血管内皮与微循环"},
    "D": {"label": "阴阳-昼夜节律", "concept": "阴阳", "proxy": "昼夜节律稳态"},
    "E": {"label": "脏腑-神经内分泌(HPA)", "concept": "脏腑", "proxy": "HPA 轴与应激稳态"},
    "F": {"label": "正邪-炎症负荷", "concept": "正邪", "proxy": "慢性低度炎症"},
    "G": {"label": "神-情志(自主神经)", "concept": "神", "proxy": "自主神经平衡"},
    "H": {"label": "先天-肾精(表观遗传)", "concept": "先天之本", "proxy": "表观遗传完整性"},
}

ALL_AXES = list(AXIS_META.keys())


@dataclass
class AxisScore:
    """单轴评分结果。

    score: 0-100，稳态越好分越高；无数据时为 None（measured=False）。
    status: measured_normal / measured_risk / unmeasured。
    sources: 实际参与计算的真实输入键列表（端到端追溯用）。
    """

    axis: str
    label: str
    score: float | None = None
    status: str = "unmeasured"
    measured: bool = False
    sources: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "axis": self.axis,
            "label": self.label,
            "score": self.score,
            "status": self.status,
            "measured": self.measured,
            "sources": self.sources,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# 透明小工具
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _gauss_penalty(value: float, ideal: float, tol: float, full_penalty: float) -> float:
    """对称偏离惩罚：|value-ideal| <= tol 不扣分；线性增长到 full_penalty。

    用于 BMI、睡眠时长等「越接近理想越好、双向偏离都差」的指标。
    """
    dev = abs(value - ideal)
    if dev <= tol:
        return 0.0
    return _clamp(full_penalty * (dev - tol) / max(full_penalty, 1.0) * 0.0 + full_penalty * min(1.0, (dev - tol) / (tol + 1e-9) / 4.0))


# ---------------------------------------------------------------------------
# A 气化-自噬 (AMPK-mTOR) — 血糖代谢稳态
# ---------------------------------------------------------------------------

def _score_axis_A(bm: dict, is_male: bool = True) -> AxisScore:
    src = []
    penalty = 0.0
    # 空腹血糖
    g = bm.get("glucose")
    if g is not None:
        src.append("glucose")
        if g > 7.0:
            penalty += 28
        elif g > 6.1:
            penalty += 18
        elif g > 5.6:
            penalty += 8
    h = bm.get("hba1c")
    if h is not None:
        src.append("hba1c")
        if h >= 6.5:
            penalty += 22
        elif h >= 6.0:
            penalty += 12
        elif h >= 5.8:
            penalty += 6
    w = bm.get("waist_cm")
    if w is not None:
        src.append("waist_cm")
        hi = 102 if is_male else 88
        if w > hi + 10:
            penalty += 20
        elif w > hi:
            penalty += 10
    tg = bm.get("triglycerides")
    if tg is not None:
        src.append("triglycerides")
        if tg >= 2.3:
            penalty += 16
        elif tg >= 1.7:
            penalty += 8
    bmi = bm.get("bmi")
    if bmi is not None:
        src.append("bmi")
        if bmi >= 28 or bmi < 17:
            penalty += 18
        elif bmi >= 25 or bmi < 18.5:
            penalty += 10
    if not src:
        return AxisScore("A", AXIS_META["A"]["label"], measured=False,
                         note="无血糖/糖化/腰围/血脂/BMI 输入，A 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("A", AXIS_META["A"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="AMPK-mTOR 稳态代理：偏离健康血糖/体脂区间越多，自噬流越受抑")


# ---------------------------------------------------------------------------
# B 气血-线粒体能量 (NAD+/mtDNA) — 蛋白/脂质能量代谢 + 静息心率
# ---------------------------------------------------------------------------

def _score_axis_B(bm: dict, wearable: dict | None = None) -> AxisScore:
    src = []
    penalty = 0.0
    hdl = bm.get("hdl")
    if hdl is not None:
        src.append("hdl")
        low = 1.0  # 男性阈值下限，女性 1.3 已在 caller 处理；此处统一用 1.0 简化
        if hdl < 0.9:
            penalty += 16
        elif hdl < 1.0:
            penalty += 8
    tg = bm.get("triglycerides")
    if tg is not None:
        src.append("triglycerides")
        if tg >= 2.3:
            penalty += 16
        elif tg >= 1.7:
            penalty += 8
    homo = bm.get("homocysteine")
    if homo is not None:
        src.append("homocysteine")
        if homo >= 15:
            penalty += 14
        elif homo >= 10:
            penalty += 7
    rh = (wearable or {}).get("resting_hr")
    if rh is not None:
        src.append("resting_hr")
        if rh >= 90:
            penalty += 10
        elif rh >= 80:
            penalty += 5
    if not src:
        return AxisScore("B", AXIS_META["B"]["label"], measured=False,
                         note="无 HDL/甘油三酯/同型半胱氨酸/静息心率输入，B 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("B", AXIS_META["B"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="线粒体能量代谢代理：血脂模式与静息心率反映基础代谢与心肺储备")


# ---------------------------------------------------------------------------
# C 络脉-内皮微循环 — 血压 + 炎症 + 同型半胱氨酸
# ---------------------------------------------------------------------------

def _score_axis_C(bm: dict) -> AxisScore:
    src = []
    penalty = 0.0
    sbp = bm.get("sbp")
    dbp = bm.get("dbp")
    if sbp is not None:
        src.append("sbp")
        if sbp >= 140:
            penalty += 22
        elif sbp >= 130:
            penalty += 12
        elif sbp >= 120:
            penalty += 6
    if dbp is not None:
        src.append("dbp")
        if dbp >= 90:
            penalty += 12
        elif dbp >= 85:
            penalty += 6
    hs = bm.get("hs_crp")
    if hs is not None:
        src.append("hs_crp")
        if hs > 3.0:
            penalty += 15
        elif hs > 1.0:
            penalty += 8
    homo = bm.get("homocysteine")
    if homo is not None:
        src.append("homocysteine")
        if homo >= 15:
            penalty += 12
        elif homo >= 10:
            penalty += 6
    if not src:
        return AxisScore("C", AXIS_META["C"]["label"], measured=False,
                         note="无血压/炎症/同型半胱氨酸输入，C 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("C", AXIS_META["C"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="内皮微循环代理：血压负荷与炎症共同反映络脉通畅度")


# ---------------------------------------------------------------------------
# D 阴阳-昼夜节律 — 睡眠中点抖动 / 时长 / 社会时差（需可穿戴睡眠）
# ---------------------------------------------------------------------------

def _score_axis_D(wearable: dict | None = None, symptoms: list | None = None) -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    jitter = w.get("sleep_midpoint_jitter")  # 每日睡眠中点标准差（分钟）
    if jitter is not None:
        src.append("sleep_midpoint_jitter")
        if jitter >= 90:
            penalty += 25
        elif jitter >= 60:
            penalty += 15
        elif jitter >= 30:
            penalty += 8
    duration = w.get("sleep_duration_h")  # 平均睡眠时长（小时）
    if duration is not None:
        src.append("sleep_duration_h")
        if duration < 5.5 or duration > 9.5:
            penalty += 15
        elif duration < 6.5 or duration > 8.5:
            penalty += 8
    sjl = w.get("social_jetlag_h")  # 社会时差（周末-工作日睡眠中点差，小时）
    if sjl is not None:
        src.append("social_jetlag_h")
        if sjl >= 2.0:
            penalty += 15
        elif sjl >= 1.0:
            penalty += 8
    if not src:
        return AxisScore("D", AXIS_META["D"]["label"], measured=False,
                         note="无睡眠节律数据（需可穿戴睡眠/作息记录），D 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("D", AXIS_META["D"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="昼夜节律代理：睡眠规律性与社会时差反映阴阳动态平衡")


# ---------------------------------------------------------------------------
# E 脏腑-神经内分泌 (HPA) — HRV + 静息心率 + 压力症状
# ---------------------------------------------------------------------------

def _score_axis_E(wearable: dict | None = None, symptoms: list | None = None) -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    rmssd = w.get("hrv_rmssd")  # ms
    if rmssd is not None:
        src.append("hrv_rmssd")
        if rmssd < 15:
            penalty += 22
        elif rmssd < 25:
            penalty += 12
        elif rmssd < 35:
            penalty += 6
    rh = w.get("resting_hr")
    if rh is not None:
        src.append("resting_hr")
        if rh >= 90:
            penalty += 10
        elif rh >= 80:
            penalty += 5
    stress_kw = {"压力大", "焦虑", "失眠", "易怒", "疲劳", "倦怠", "紧张"}
    sym = symptoms or []
    hit = [s for s in sym if any(k in str(s) for k in stress_kw)]
    if hit:
        src.append("tcm_symptoms")
        penalty += min(15, 4 * len(hit))
    if not src:
        return AxisScore("E", AXIS_META["E"]["label"], measured=False,
                         note="无 HRV/静息心率/压力症状输入，E 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("E", AXIS_META["E"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="HPA/自主神经代理：HRV 降低与压力症状反映脏腑应激稳态")


# ---------------------------------------------------------------------------
# F 正邪-炎症负荷 — hs-CRP / IL-6
# ---------------------------------------------------------------------------

def _score_axis_F(bm: dict) -> AxisScore:
    src = []
    penalty = 0.0
    hs = bm.get("hs_crp")
    if hs is not None:
        src.append("hs_crp")
        if hs > 3.0:
            penalty += 30
        elif hs > 1.0:
            penalty += 15
    il6 = bm.get("il6")
    if il6 is not None:
        src.append("il6")
        if il6 > 3.0:
            penalty += 25
        elif il6 > 1.8:
            penalty += 12
    if not src:
        return AxisScore("F", AXIS_META["F"]["label"], measured=False,
                         note="无 hs-CRP/IL-6 输入，F 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("F", AXIS_META["F"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="炎症负荷代理：hs-CRP/IL-6 反映正邪（炎症-修复）平衡")


# ---------------------------------------------------------------------------
# G 神-情志 (自主神经) — HRV(RMSSD) + 睡眠规律性
# ---------------------------------------------------------------------------

def _score_axis_G(wearable: dict | None = None) -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    rmssd = w.get("hrv_rmssd")
    if rmssd is not None:
        src.append("hrv_rmssd")
        if rmssd < 15:
            penalty += 22
        elif rmssd < 25:
            penalty += 12
        elif rmssd < 35:
            penalty += 6
    jitter = w.get("sleep_midpoint_jitter")
    if jitter is not None:
        src.append("sleep_midpoint_jitter")
        if jitter >= 90:
            penalty += 15
        elif jitter >= 60:
            penalty += 8
    if not src:
        return AxisScore("G", AXIS_META["G"]["label"], measured=False,
                         note="无 HRV/睡眠规律性输入，G 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("G", AXIS_META["G"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="自主神经平衡代理：HRV 与睡眠规律性反映神/情志稳态")


# ---------------------------------------------------------------------------
# H 先天-肾精 (表观遗传) — 表观遗传年龄偏移 + 端粒(可选)
# ---------------------------------------------------------------------------

def _score_axis_H(bioage_delta: float | None = None, bm: dict | None = None) -> AxisScore:
    src = []
    penalty = 0.0
    if bioage_delta is not None:
        src.append("bioage_delta")
        if bioage_delta >= 6.0:
            penalty += 30
        elif bioage_delta >= 3.0:
            penalty += 18
        elif bioage_delta >= 0.5:
            penalty += 8
    tl = (bm or {}).get("telomere_length")
    if tl is not None:
        src.append("telomere_length")
        if tl < 0.8:
            penalty += 15
        elif tl < 1.0:
            penalty += 8
    if not src:
        return AxisScore("H", AXIS_META["H"]["label"], measured=False,
                         note="无表观遗传年龄偏移/端粒输入，H 轴未测量")
    score = _clamp(100.0 - penalty)
    return AxisScore("H", AXIS_META["H"]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src,
                     note="表观遗传完整性代理：生物学年龄偏移反映先天之本耗损")


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def score_axis(
    axis: str,
    *,
    biomarkers: dict | None = None,
    wearable: dict | None = None,
    symptoms: list | None = None,
    bioage_delta: float | None = None,
    is_male: bool = True,
) -> AxisScore:
    """对单轴打分。缺失数据返回 measured=False 的结果。"""
    bm = biomarkers or {}
    if axis == "A":
        return _score_axis_A(bm, is_male)
    if axis == "B":
        return _score_axis_B(bm, wearable)
    if axis == "C":
        return _score_axis_C(bm)
    if axis == "D":
        return _score_axis_D(wearable, symptoms)
    if axis == "E":
        return _score_axis_E(wearable, symptoms)
    if axis == "F":
        return _score_axis_F(bm)
    if axis == "G":
        return _score_axis_G(wearable)
    if axis == "H":
        return _score_axis_H(bioage_delta, bm)
    raise ValueError(f"未知轴: {axis}")


def score_all_axes(
    *,
    biomarkers: dict | None = None,
    wearable: dict | None = None,
    symptoms: list | None = None,
    bioage_delta: float | None = None,
    is_male: bool = True,
) -> dict[str, AxisScore]:
    """对所有八轴打分，返回 {axis: AxisScore}。"""
    out: dict[str, AxisScore] = {}
    for ax in ALL_AXES:
        out[ax] = score_axis(
            ax, biomarkers=biomarkers, wearable=wearable,
            symptoms=symptoms, bioage_delta=bioage_delta, is_male=is_male,
        )
    return out


def axis_scores_to_dict(scores: dict[str, AxisScore]) -> dict:
    return {ax: s.to_dict() for ax, s in scores.items()}


if __name__ == "__main__":
    # 演示：一份偏不健康的体检 + 可穿戴数据，应让多数轴 measurable
    demo_bm = {
        "glucose": 6.4, "hba1c": 6.1, "waist_cm": 98, "triglycerides": 2.0,
        "bmi": 26.5, "hdl": 0.95, "sbp": 135, "dbp": 88, "hs_crp": 2.2,
    }
    demo_wearable = {"hrv_rmssd": 22, "resting_hr": 82, "sleep_midpoint_jitter": 65,
                     "sleep_duration_h": 6.0, "social_jetlag_h": 1.5}
    res = score_all_axes(biomarkers=demo_bm, wearable=demo_wearable,
                         symptoms=["疲劳", "焦虑"], bioage_delta=4.0, is_male=True)
    for ax, s in res.items():
        print(f"{ax} {s.label}: score={s.score} measured={s.measured} src={s.sources}")
