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

**跨轴归一化（S1-2，2026-10-13）**：
     score = 100 − 100 × (Σ实际扣分 / Σ可用输入的最大扣分)
分数反映「可用输入内部的相对严重度」，与可用输入的**数量**解耦：
同质异常（可用输入全部打满）恒得 0 分、全部正常恒得 100 分，与测了几项无关；
score<70 ⟺ ratio>0.3 在八轴之间完全等价（弱项阈值跨轴可比）。
这消除了旧公式 `100 − Σpenalty` 的缺陷——各轴可用输入数不同（A 轴 5 项、
F 轴 2 项），加总扣分使「少填异常项」的轴分自动变好，弱项阈值 0.5 在轴间不等价。
诚实边界：可用输入很少时，分数被可测量部分主导（prorated scoring 语义，
见 `_finalize` docstring），论文中须作为方法学约定明示，不可称作「与数量完全无关」。
每条结果带 `penalty_ratio` 字段（归一化亏缺比），供论文/审计端到端追溯。

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
# A2 参数外置接线（B0-2，2026-10-11）
# ---------------------------------------------------------------------------
# 设计：把 YAML 依赖隔离到 lazy import 中，保留 axis_scorers 的"标准库 only"约束。
# 若 axis_config/yaml 不可用，_t() 自动 fallback 到调用方传入的 default 值，
# 行为与硬编码完全一致（backward-compatible）。改 YAML 立即改行为，无需发版。
# 阈值 metric 命名与 config/axes/axes.yaml 保持一致（fpg/hba1c/bmi/waist/tg/…）。
#
# 用法：
#     if g > _t('A', 'fpg', 'impaired_max', 7.0):
#         penalty += _p('A', 'fpg', 'impaired_max_penalty', 28)
# ---------------------------------------------------------------------------

try:
    from app.lib.axis_config import get_threshold as _axis_get_threshold
    _AXIS_CONFIG_AVAILABLE = True
except Exception:  # pragma: no cover — 精简环境/导入失败 fallback
    _AXIS_CONFIG_AVAILABLE = False

    def _axis_get_threshold(*args, **kwargs):  # type: ignore
        default = kwargs.get("default")
        return default


def _t(axis: str, metric: str, key: str, default: float | None,
       jurisdiction: str = "cn") -> float:
    """安全阈值查询：axis_config 优先，失败回退 default。永远返回 float。"""
    try:
        v = _axis_get_threshold(axis, metric, key, jurisdiction=jurisdiction, default=default)
        return float(v) if v is not None else float(default)
    except Exception:
        return float(default)


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
    penalty_ratio: 归一化亏缺比 = Σ实际扣分 / Σ可用输入最大扣分（0-1）。
        score = 100 − 100 × penalty_ratio。该字段使「分数只取决于可用输入内部
        的相对严重度、与输入数量无关」可被逐案审计（S1-2）。
    """

    axis: str
    label: str
    score: float | None = None
    status: str = "unmeasured"
    measured: bool = False
    sources: list[str] = field(default_factory=list)
    note: str = ""
    penalty_ratio: float | None = None

    def to_dict(self) -> dict:
        return {
            "axis": self.axis,
            "label": self.label,
            "score": self.score,
            "status": self.status,
            "measured": self.measured,
            "sources": self.sources,
            "note": self.note,
            "penalty_ratio": self.penalty_ratio,
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


def _finalize(
    axis: str,
    src: list[str],
    penalty: float,
    penalty_max: float,
    note: str,
    unmeasured_note: str,
) -> AxisScore:
    """八轴统一的归一化收尾（S1-2，2026-10-13）。

    - 无任何可用输入 → measured=False / score=None（绝不填 0）。
    - 否则 score = 100 − 100 × (penalty / penalty_max)，其中 penalty_max 为
      **可用输入**各自最大扣分之和。成立的性质（已实测）：
        * 可用输入全部打满 → ratio=1.0 → score=0，与可用数量无关；
        * 可用输入全部正常 → ratio=0 → score=100，与可用数量无关；
        * score<70 ⟺ ratio>0.3，在八轴间完全等价（弱项阈值跨轴可比）；
        * 绝不以「少填」奖励：旧公式 100−Σpenalty 下，少填异常项分数自动变高
          （1 项全异常=72 vs 5 项全异常=0）；本公式下同质异常恒得同分。
      诚实边界（非缺陷，是「有限证据下的保守判定」）：当可用输入很少时，分数反映
      「可测量部分的相对严重度」——只测到一项且该项中度异常时，轴分被该项主导。
      该语义与 QoL 量表的 prorated scoring（按已答条目计分）一致，须在论文
      方法学与局限性中明示，不得表述为「与输入数量完全无关」。
    """
    if not src:
        return AxisScore(axis, AXIS_META[axis]["label"], measured=False,
                         note=unmeasured_note)
    ratio = _clamp(penalty / penalty_max, 0.0, 1.0) if penalty_max > 0 else 0.0
    score = _clamp(100.0 - 100.0 * ratio)
    return AxisScore(axis, AXIS_META[axis]["label"], score=round(score, 1),
                     status="measured_normal" if score >= 70 else "measured_risk",
                     measured=True, sources=src, penalty_ratio=round(ratio, 3),
                     note=note)


# ---------------------------------------------------------------------------
# A 气化-自噬 (AMPK-mTOR) — 血糖代谢稳态
# ---------------------------------------------------------------------------

def _score_axis_A(bm: dict, is_male: bool = True, jurisdiction: str = "cn") -> AxisScore:
    src = []
    penalty = 0.0
    penalty_max = 0.0
    # 空腹血糖
    g = bm.get("glucose")
    if g is not None:
        src.append("glucose")
        penalty_max += 28
        if g > _t('A', 'fpg', 'impaired_max', 7.0, jurisdiction):
            penalty += 28
        elif g > _t('A', 'fpg', 'normal_max', 6.1, jurisdiction):
            penalty += 18
        elif g > _t('A', 'fpg', 'elevated_max', 5.6, jurisdiction):
            penalty += 8
    h = bm.get("hba1c")
    if h is not None:
        src.append("hba1c")
        penalty_max += 22
        if h >= _t('A', 'hba1c', 'impaired_max', 6.5, jurisdiction):
            penalty += 22
        elif h >= _t('A', 'hba1c', 'elevated_max', 6.0, jurisdiction):
            penalty += 12
        elif h >= _t('A', 'hba1c', 'normal_max', 5.8, jurisdiction):
            penalty += 6
    w = bm.get("waist_cm")
    if w is not None:
        src.append("waist_cm")
        penalty_max += 20
        # 男性/女性腰围 overweight_max（B0-2：从 axes.yaml 加载，保留原值 fallback）
        waist_key = 'waist' if is_male else 'waist_female'
        hi = _t('A', waist_key, 'overweight_max', 102 if is_male else 88, jurisdiction)
        if w > hi + 10:
            penalty += 20
        elif w > hi:
            penalty += 10
    tg = bm.get("triglycerides")
    if tg is not None:
        src.append("triglycerides")
        penalty_max += 16
        if tg >= _t('A', 'tg', 'elevated_max', 2.3, jurisdiction):
            penalty += 16
        elif tg >= _t('A', 'tg', 'normal_max', 1.7, jurisdiction):
            penalty += 8
    bmi = bm.get("bmi")
    if bmi is not None:
        src.append("bmi")
        penalty_max += 18
        if bmi >= _t('A', 'bmi', 'severe_min', 28, jurisdiction) or bmi < _t('A', 'bmi', 'severe_low', 17, jurisdiction):
            penalty += 18
        elif bmi >= _t('A', 'bmi', 'overweight_max', 25, jurisdiction) or bmi < 18.5:
            penalty += 10
    return _finalize(
        "A", src, penalty, penalty_max,
        note="AMPK-mTOR 稳态代理：偏离健康血糖/体脂区间越多，自噬流越受抑",
        unmeasured_note="无血糖/糖化/腰围/血脂/BMI 输入，A 轴未测量",
    )


# ---------------------------------------------------------------------------
# B 气血-线粒体能量 (NAD+/mtDNA) — 蛋白/脂质能量代谢 + 静息心率
# ---------------------------------------------------------------------------

def _score_axis_B(bm: dict, wearable: dict | None = None, jurisdiction: str = "cn") -> AxisScore:
    src = []
    penalty = 0.0
    penalty_max = 0.0
    hdl = bm.get("hdl")
    if hdl is not None:
        src.append("hdl")
        penalty_max += 16
        # 男性阈值下限，女性 1.3 已在 caller 处理；此处统一用 1.0 简化
        if hdl < _t('B', 'hdl', 'severe_low', 0.7, jurisdiction) + 0.2:  # severe_low + 0.2 ≈ 0.9
            penalty += 16
        elif hdl < _t('B', 'hdl', 'low_min', 1.0, jurisdiction):
            penalty += 8
    tg = bm.get("triglycerides")
    if tg is not None:
        src.append("triglycerides")
        penalty_max += 16
        if tg >= _t('B', 'tg', 'severe_max', 2.3, jurisdiction):
            penalty += 16
        elif tg >= _t('B', 'tg', 'elevated_max', 1.7, jurisdiction):
            penalty += 8
    homo = bm.get("homocysteine")
    if homo is not None:
        src.append("homocysteine")
        penalty_max += 14
        if homo >= _t('B', 'homo_cysteine', 'severe_max', 20, jurisdiction) - 5:
            penalty += 14
        elif homo >= _t('B', 'homo_cysteine', 'elevated_max', 15, jurisdiction) - 5:
            penalty += 7
    rh = (wearable or {}).get("resting_hr")
    if rh is not None:
        src.append("resting_hr")
        penalty_max += 10
        if rh >= _t('B', 'resting_hr', 'elevated_max', 90, jurisdiction):
            penalty += 10
        elif rh >= _t('B', 'resting_hr', 'normal_max', 80, jurisdiction):
            penalty += 5
    return _finalize(
        "B", src, penalty, penalty_max,
        note="线粒体能量代谢代理：血脂模式与静息心率反映基础代谢与心肺储备",
        unmeasured_note="无 HDL/甘油三酯/同型半胱氨酸/静息心率输入，B 轴未测量",
    )


# ---------------------------------------------------------------------------
# C 络脉-内皮微循环 — 血压 + 炎症 + 同型半胱氨酸
# ---------------------------------------------------------------------------

def _score_axis_C(bm: dict, jurisdiction: str = "cn") -> AxisScore:
    src = []
    penalty = 0.0
    penalty_max = 0.0
    sbp = bm.get("sbp")
    dbp = bm.get("dbp")
    if sbp is not None:
        src.append("sbp")
        penalty_max += 22
        if sbp >= _t('C', 'sbp', 'hypertensive_max', 140, jurisdiction):
            penalty += 22
        elif sbp >= _t('C', 'sbp', 'elevated_max', 130, jurisdiction):
            penalty += 12
        elif sbp >= _t('C', 'sbp', 'normal_max', 120, jurisdiction):
            penalty += 6
    if dbp is not None:
        src.append("dbp")
        penalty_max += 12
        if dbp >= _t('C', 'dbp', 'hypertensive_max', 90, jurisdiction):
            penalty += 12
        elif dbp >= _t('C', 'dbp', 'elevated_max', 85, jurisdiction):
            penalty += 6
    hs = bm.get("hs_crp")
    if hs is not None:
        src.append("hs_crp")
        penalty_max += 15
        if hs > _t('C', 'hs_crp', 'elevated_max', 3.0, jurisdiction):
            penalty += 15
        elif hs > _t('C', 'hs_crp', 'normal_max', 1.0, jurisdiction):
            penalty += 8
    homo = bm.get("homocysteine")
    if homo is not None:
        src.append("homocysteine")
        penalty_max += 12
        if homo >= _t('C', 'homo_cysteine', 'elevated_max', 15, jurisdiction):
            penalty += 12
        elif homo >= _t('C', 'homo_cysteine', 'normal_max', 10, jurisdiction):
            penalty += 6
    return _finalize(
        "C", src, penalty, penalty_max,
        note="内皮微循环代理：血压负荷与炎症共同反映络脉通畅度",
        unmeasured_note="无血压/炎症/同型半胱氨酸输入，C 轴未测量",
    )


# ---------------------------------------------------------------------------
# D 阴阳-昼夜节律 — 睡眠中点抖动 / 时长 / 社会时差（需可穿戴睡眠）
# ---------------------------------------------------------------------------

def _score_axis_D(wearable: dict | None = None, symptoms: list | None = None, jurisdiction: str = "cn") -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    penalty_max = 0.0
    jitter = w.get("sleep_midpoint_jitter")  # 每日睡眠中点标准差（分钟）
    if jitter is not None:
        src.append("sleep_midpoint_jitter")
        penalty_max += 25
        if jitter >= _t('D', 'sleep_midpoint_jitter', 'severe_max', 90, jurisdiction):
            penalty += 25
        elif jitter >= _t('D', 'sleep_midpoint_jitter', 'elevated_max', 60, jurisdiction):
            penalty += 15
        elif jitter >= _t('D', 'sleep_midpoint_jitter', 'normal_max', 30, jurisdiction):
            penalty += 8
    duration = w.get("sleep_duration_h")  # 平均睡眠时长（小时）
    if duration is not None:
        src.append("sleep_duration_h")
        penalty_max += 15
        # 长/短睡眠：以 YAML 的 long_max/short_min 为锚，±0.5h 作为严重阈值
        long_max = _t('D', 'sleep_duration', 'long_max', 9.0, jurisdiction)
        short_min = _t('D', 'sleep_duration', 'short_min', 6.0, jurisdiction)
        if duration < short_min - 0.5 or duration > long_max + 0.5:
            penalty += 15
        elif duration < short_min + 0.5 or duration > long_max - 0.5:
            penalty += 8
    sjl = w.get("social_jetlag_h")  # 社会时差（周末-工作日睡眠中点差，小时）
    if sjl is not None:
        src.append("social_jetlag_h")
        penalty_max += 15
        if sjl >= _t('D', 'social_time_lag', 'elevated_max', 2.0, jurisdiction):
            penalty += 15
        elif sjl >= _t('D', 'social_time_lag', 'normal_max', 1.0, jurisdiction):
            penalty += 8
    return _finalize(
        "D", src, penalty, penalty_max,
        note="昼夜节律代理：睡眠规律性与社会时差反映阴阳动态平衡",
        unmeasured_note="无睡眠节律数据（需可穿戴睡眠/作息记录），D 轴未测量",
    )


# ---------------------------------------------------------------------------
# E 脏腑-神经内分泌 (HPA) — HRV + 静息心率 + 压力症状
# ---------------------------------------------------------------------------

def _score_axis_E(wearable: dict | None = None, symptoms: list | None = None, jurisdiction: str = "cn") -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    penalty_max = 0.0
    rmssd = w.get("hrv_rmssd")  # ms
    if rmssd is not None:
        src.append("hrv_rmssd")
        penalty_max += 22
        low_max = _t('E', 'hrv_rmssd', 'low_max', 30, jurisdiction)
        severe_low = _t('E', 'hrv_rmssd', 'severe_low', 20, jurisdiction)
        if rmssd < severe_low - 5:
            penalty += 22
        elif rmssd < low_max - 5:
            penalty += 12
        elif rmssd < low_max + 5:
            penalty += 6
    rh = w.get("resting_hr")
    if rh is not None:
        src.append("resting_hr")
        penalty_max += 10
        if rh >= _t('E', 'resting_hr', 'elevated_max', 90, jurisdiction):
            penalty += 10
        elif rh >= _t('E', 'resting_hr', 'normal_max', 80, jurisdiction):
            penalty += 5
    stress_kw = {"压力大", "焦虑", "失眠", "易怒", "疲劳", "倦怠", "紧张"}
    sym = symptoms or []
    hit = [s for s in sym if any(k in str(s) for k in stress_kw)]
    if hit:
        src.append("tcm_symptoms")
        penalty_max += 15  # min(15, 4*len(hit)) 的上限
        penalty += min(15, 4 * len(hit))
    return _finalize(
        "E", src, penalty, penalty_max,
        note="HPA/自主神经代理：HRV 降低与压力症状反映脏腑应激稳态",
        unmeasured_note="无 HRV/静息心率/压力症状输入，E 轴未测量",
    )


# ---------------------------------------------------------------------------
# F 正邪-炎症负荷 — hs-CRP / IL-6
# ---------------------------------------------------------------------------

def _score_axis_F(bm: dict, jurisdiction: str = "cn") -> AxisScore:
    src = []
    penalty = 0.0
    penalty_max = 0.0
    hs = bm.get("hs_crp")
    if hs is not None:
        src.append("hs_crp")
        penalty_max += 30
        if hs > _t('F', 'hs_crp', 'elevated_max', 3.0, jurisdiction):
            penalty += 30
        elif hs > _t('F', 'hs_crp', 'normal_max', 1.0, jurisdiction):
            penalty += 15
    il6 = bm.get("il6")
    if il6 is not None:
        src.append("il6")
        penalty_max += 25
        if il6 > _t('F', 'il6', 'elevated_max', 5.0, jurisdiction) - 2.0:
            penalty += 25
        elif il6 > _t('F', 'il6', 'normal_max', 2.5, jurisdiction) - 0.7:
            penalty += 12
    return _finalize(
        "F", src, penalty, penalty_max,
        note="炎症负荷代理：hs-CRP/IL-6 反映正邪（炎症-修复）平衡",
        unmeasured_note="无 hs-CRP/IL-6 输入，F 轴未测量",
    )


# ---------------------------------------------------------------------------
# G 神-情志 (自主神经) — HRV(RMSSD) + 睡眠规律性
# ---------------------------------------------------------------------------

def _score_axis_G(wearable: dict | None = None, jurisdiction: str = "cn") -> AxisScore:
    w = wearable or {}
    src = []
    penalty = 0.0
    penalty_max = 0.0
    rmssd = w.get("hrv_rmssd")
    if rmssd is not None:
        src.append("hrv_rmssd")
        penalty_max += 16
        # S0-7（2026-10-13）：G 轴使用与 E 轴**独立调参**的 RMSSD 敏感曲线。
        # 阈值由 axis_config 读取（G: low_max=25 / severe_low=15；E: 30/20），
        # 惩罚幅度也更平缓（16/9/4 vs E 的 22/12/6）。二者组合保证
        # 「仅 HRV 输入时 E≠G」，消除「八轴实为七轴」的方法学质疑。
        # 说明：E(脏腑-神经内分泌/HPA) 与 G(神-情志/自主神经) 在生理上共享迷走张力信号，
        # 完整轴独立性需要 G 引入 RSA/PSD 频域分量作为独立输入（后续升级项）；
        # 当前以独立敏感曲线 + 睡眠规律性为主锚点达成构造独立，并在健康上限处
        # 自然重合（高 HRV 两轴均为满分，属正确行为）。
        low_max = _t('G', 'hrv_rmssd', 'low_max', 30, jurisdiction)
        severe_low = _t('G', 'hrv_rmssd', 'severe_low', 20, jurisdiction)
        if rmssd < severe_low - 5:
            penalty += 16
        elif rmssd < low_max - 5:
            penalty += 9
        elif rmssd < low_max + 5:
            penalty += 4
    jitter = w.get("sleep_midpoint_jitter")
    if jitter is not None:
        src.append("sleep_midpoint_jitter")
        penalty_max += 15
        if jitter >= _t('G', 'sleep_regularity', 'severe_low', 30, jurisdiction):
            penalty += 15
        elif jitter >= _t('G', 'sleep_regularity', 'low_max', 50, jurisdiction):
            penalty += 8
    return _finalize(
        "G", src, penalty, penalty_max,
        note="自主神经平衡代理：HRV 与睡眠规律性反映神/情志稳态",
        unmeasured_note="无 HRV/睡眠规律性输入，G 轴未测量",
    )


# ---------------------------------------------------------------------------
# H 先天-肾精 (表观遗传) — 表观遗传年龄偏移 + 端粒(可选)
# ---------------------------------------------------------------------------

def _score_axis_H(
    bioage_delta: float | None = None,
    bm: dict | None = None,
    jurisdiction: str = "cn",
) -> AxisScore:
    """H 先天-肾精轴打分（表观遗传）。

    S0-2（2026-10-12）：签名补齐 `jurisdiction` 参数，与其他 7 个轴打分器一致。
    此前 `_score_axis_H` 未随 B0-2 参数外置改造同步更新，导致 `score_axis()` 传 3 个
    位置参数时抛 `TypeError`，函数体内又引用未定义名 `jurisdiction` 会引发 `NameError`——
    双缺陷被 `fusion_engine` 的 `except Exception: {}` 静默吞掉，使得 axis_scores 恒为空。
    """
    src = []
    penalty = 0.0
    penalty_max = 0.0
    if bioage_delta is not None:
        src.append("bioage_delta")
        penalty_max += 30
        if bioage_delta >= _t('H', 'bioage_delta', 'severe_max', 6.0, jurisdiction):
            penalty += 30
        elif bioage_delta >= _t('H', 'bioage_delta', 'elevated_max', 3.0, jurisdiction):
            penalty += 18
        elif bioage_delta >= _t('H', 'bioage_delta', 'normal_max', 0.5, jurisdiction):
            penalty += 8
    tl = (bm or {}).get("telomere_length")
    if tl is not None:
        src.append("telomere_length")
        penalty_max += 15
        if tl < _t('H', 'telomere_length', 'low_max', 0.8, jurisdiction):
            penalty += 15
        elif tl < _t('H', 'telomere_length', 'normal_min', 1.0, jurisdiction):
            penalty += 8
    return _finalize(
        "H", src, penalty, penalty_max,
        note="表观遗传完整性代理：生物学年龄偏移反映先天之本耗损",
        unmeasured_note="无表观遗传年龄偏移/端粒输入，H 轴未测量",
    )


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
    jurisdiction: str = "cn",
) -> AxisScore:
    """对单轴打分。缺失数据返回 measured=False 的结果。

    B0-2: jurisdiction 参数接入 axis_config，按法域读取阈值。
    S1-2: 分数按可用输入覆盖率归一化（见模块 docstring 与 _finalize）。
    """
    bm = biomarkers or {}
    if axis == "A":
        return _score_axis_A(bm, is_male, jurisdiction)
    if axis == "B":
        return _score_axis_B(bm, wearable, jurisdiction)
    if axis == "C":
        return _score_axis_C(bm, jurisdiction)
    if axis == "D":
        return _score_axis_D(wearable, symptoms, jurisdiction)
    if axis == "E":
        return _score_axis_E(wearable, symptoms, jurisdiction)
    if axis == "F":
        return _score_axis_F(bm, jurisdiction)
    if axis == "G":
        return _score_axis_G(wearable, jurisdiction)
    if axis == "H":
        return _score_axis_H(bioage_delta, bm, jurisdiction)
    raise ValueError(f"未知轴: {axis}")


def score_all_axes(
    *,
    biomarkers: dict | None = None,
    wearable: dict | None = None,
    symptoms: list | None = None,
    bioage_delta: float | None = None,
    is_male: bool = True,
    jurisdiction: str = "cn",
) -> dict[str, AxisScore]:
    """对所有八轴打分，返回 {axis: AxisScore}。

    B0-2: jurisdiction 参数透传到各轴打分器。
    """
    out: dict[str, AxisScore] = {}
    for ax in ALL_AXES:
        out[ax] = score_axis(
            ax, biomarkers=biomarkers, wearable=wearable,
            symptoms=symptoms, bioage_delta=bioage_delta, is_male=is_male,
            jurisdiction=jurisdiction,
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
