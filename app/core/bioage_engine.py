"""生物学年龄 / 八轴「代谢-炎症轴」量化引擎
============================================

借鉴开源思路（PhenoAge / BioAge toolkit 的「多生物标志物→年龄偏移」范式），
但明确区分：

- **真实 PhenoAge**（Levine 2018, epigenetic clock）依赖 DNA 甲基化（DNAm CpG），
  HealthLens 不采集、也不伪造组学数据（遵循零成本 + 去医疗化边界）。
- 本模块是**透明、可解释的体检指标代理（wellness proxy）**：用常规血检/体测指标，
  按公开循证区间估算一个「生物学年龄偏移」与「代谢-炎症轴稳态分（0-100）」。
  任何结果都标注 `not_clinical=True`，仅供养生参考，不构成诊断。

量化方法（全透明，系数源自通用临床阈值，非黑箱）：
- 代谢维度：空腹血糖、HbA1c、腰围、甘油三酯、HDL、血压、BMI
- 炎症维度：hs-CRP（高敏 C 反应蛋白）
每项按偏离健康区间的程度给出「年龄偏移」(±年) 与「轴扣分」(0-100 起扣)，
叠加得总偏移与轴分。

参考（仅方法论，非数据依赖）：
- PhenoAge: Levine ME et al., Aging (Albany NY), 2018.
- 临床阈值：ADA 糖尿病指南 / 中国心血管病风险指南 / 中国血脂异常防治指南.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarkerResult:
    key: str
    label: str
    value: float | None
    unit: str
    status: str  # normal / borderline / high / unknown
    age_delta: float = 0.0  # 对生物学年龄的偏移（年）
    axis_penalty: float = 0.0  # 对轴分的扣分
    note: str = ""


@dataclass
class BioAgeResult:
    chrono_age: int
    bio_age: float
    delta: float  # bio_age - chrono_age（正=偏老）
    axis_score: float  # 代谢-炎症轴稳态分 0-100（高=更健康）
    markers: list[MarkerResult] = field(default_factory=list)
    not_clinical: bool = True
    method: str = (
        "HealthLens 透明体检指标代理（非 DNAm PhenoAge）："
        "代谢(血糖/HbA1c/腰围/血脂/血压/BMI)+炎症(hs-CRP) 加权启发式"
    )


# 各指标的 (正常上限/健康区间, 单位, 标签, 单点偏移系数)
# age_delta 设计为「每项中度偏离约 +1~2 年、重度偏离约 +3~5 年」的透明线性近似。
def _eval_glucose(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("glucose", "空腹血糖", v, "mmol/L", "unknown")
    if v < 5.0:
        return MarkerResult("glucose", "空腹血糖", v, "mmol/L", "normal", note="理想区间")
    if v <= 6.1:
        return MarkerResult("glucose", "空腹血糖", v, "mmol/L", "borderline",
                            age_delta=1.0, axis_penalty=8,
                            note="偏高（空腹血糖受损临界）")
    if v <= 7.0:
        return MarkerResult("glucose", "空腹血糖", v, "mmol/L", "high",
                            age_delta=3.0, axis_penalty=18, note="糖尿病前期区间")
    return MarkerResult("glucose", "空腹血糖", v, "mmol/L", "high",
                        age_delta=5.0, axis_penalty=28, note="达到糖尿病阈值")


def _eval_hba1c(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("hba1c", "糖化血红蛋白", v, "%", "unknown")
    if v < 5.7:
        return MarkerResult("hba1c", "糖化血红蛋白", v, "%", "normal", note="理想区间")
    if v <= 6.4:
        return MarkerResult("hba1c", "糖化血红蛋白", v, "%", "borderline",
                            age_delta=1.5, axis_penalty=10, note="糖尿病前期")
    return MarkerResult("hba1c", "糖化血红蛋白", v, "%", "high",
                        age_delta=4.0, axis_penalty=22, note="达到糖尿病阈值")


def _eval_hs_crp(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("hs_crp", "高敏C反应蛋白", v, "mg/L", "unknown")
    if v < 1.0:
        return MarkerResult("hs_crp", "高敏C反应蛋白", v, "mg/L", "normal", note="低炎症负荷")
    if v <= 3.0:
        return MarkerResult("hs_crp", "高敏C反应蛋白", v, "mg/L", "borderline",
                            age_delta=2.0, axis_penalty=15, note="轻-中度慢性炎症")
    return MarkerResult("hs_crp", "高敏C反应蛋白", v, "mg/L", "high",
                        age_delta=4.5, axis_penalty=30, note="显著炎症负荷（ inflammaging）")


def _eval_waist(v: float | None, is_male: bool = True) -> MarkerResult:
    if v is None:
        return MarkerResult("waist", "腰围", v, "cm", "unknown")
    hi = 102 if is_male else 88
    if v <= hi:
        return MarkerResult("waist", "腰围", v, "cm", "normal", note="腹型肥胖阈值内")
    if v <= hi + 10:
        return MarkerResult("waist", "腰围", v, "cm", "borderline",
                            age_delta=1.5, axis_penalty=10, note="腹型肥胖临界")
    return MarkerResult("waist", "腰围", v, "cm", "high",
                        age_delta=3.0, axis_penalty=20, note="腹型肥胖")


def _eval_hdl(v: float | None, is_male: bool = True) -> MarkerResult:
    if v is None:
        return MarkerResult("hdl", "高密度脂蛋白", v, "mmol/L", "unknown")
    low = 1.0 if is_male else 1.3
    if v >= low:
        return MarkerResult("hdl", "高密度脂蛋白", v, "mmol/L", "normal", note="保护性血脂充足")
    if v >= low - 0.3:
        return MarkerResult("hdl", "高密度脂蛋白", v, "mmol/L", "borderline",
                            age_delta=1.0, axis_penalty=8, note="偏低")
    return MarkerResult("hdl", "高密度脂蛋白", v, "mmol/L", "high",
                        age_delta=2.5, axis_penalty=16, note="偏低（心血管保护不足）")


def _eval_trig(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("trig", "甘油三酯", v, "mmol/L", "unknown")
    if v < 1.7:
        return MarkerResult("trig", "甘油三酯", v, "mmol/L", "normal", note="理想区间")
    if v <= 2.3:
        return MarkerResult("trig", "甘油三酯", v, "mmol/L", "borderline",
                            age_delta=1.0, axis_penalty=8, note="边缘升高")
    return MarkerResult("trig", "甘油三酯", v, "mmol/L", "high",
                        age_delta=2.5, axis_penalty=16, note="升高")


def _eval_sbp(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("sbp", "收缩压", v, "mmHg", "unknown")
    if v < 120:
        return MarkerResult("sbp", "收缩压", v, "mmHg", "normal", note="理想")
    if v <= 139:
        return MarkerResult("sbp", "收缩压", v, "mmHg", "borderline",
                            age_delta=1.5, axis_penalty=10, note="正常高值/1级高危")
    return MarkerResult("sbp", "收缩压", v, "mmHg", "high",
                        age_delta=3.5, axis_penalty=22, note="高血压区间")


def _eval_bmi(v: float | None) -> MarkerResult:
    if v is None:
        return MarkerResult("bmi", "体质指数", v, "kg/m²", "unknown")
    if 18.5 <= v <= 24.9:
        return MarkerResult("bmi", "体质指数", v, "kg/m²", "normal", note="理想区间")
    if 25.0 <= v <= 29.9 or 17.0 <= v < 18.5:
        return MarkerResult("bmi", "体质指数", v, "kg/m²", "borderline",
                            age_delta=1.5, axis_penalty=10, note="超重或偏瘦")
    return MarkerResult("bmi", "体质指数", v, "kg/m²", "high",
                        age_delta=3.0, axis_penalty=18, note="肥胖或重度偏瘦")


class BioAgeEngine:
    """生物学年龄 + 八轴代谢-炎症轴量化。"""

    def assess(
        self,
        chrono_age: int,
        *,
        is_male: bool = True,
        glucose: float | None = None,
        hba1c: float | None = None,
        hs_crp: float | None = None,
        waist_cm: float | None = None,
        hdl: float | None = None,
        triglycerides: float | None = None,
        sbp: float | None = None,
        bmi: float | None = None,
    ) -> BioAgeResult:
        """评估生物学年龄偏移与代谢-炎症轴稳态分。

        Args:
            chrono_age: 实际年龄（岁）。
            is_male: 性别（影响腰围/HDL 阈值）。
            其余为可选生物标志物；缺失项不参与评分（标记为 unknown）。
        Returns:
            BioAgeResult（含 not_clinical=True 与 method 说明）。
        """
        markers = [
            _eval_glucose(glucose),
            _eval_hba1c(hba1c),
            _eval_hs_crp(hs_crp),
            _eval_waist(waist_cm, is_male),
            _eval_hdl(hdl, is_male),
            _eval_trig(triglycerides),
            _eval_sbp(sbp),
            _eval_bmi(bmi),
        ]

        total_delta = round(sum(m.age_delta for m in markers), 1)
        axis_penalty = sum(m.axis_penalty for m in markers)
        axis_score = max(0.0, min(100.0, round(100.0 - axis_penalty, 1)))
        bio_age = round(chrono_age + total_delta, 1)

        return BioAgeResult(
            chrono_age=chrono_age,
            bio_age=bio_age,
            delta=total_delta,
            axis_score=axis_score,
            markers=markers,
        )

    def delta_band(self, delta: float) -> str:
        """把年龄偏移映射为八轴稳态描述（去医疗化表述）。"""
        if delta <= 0.5:
            return "代谢-炎症轴稳态良好，接近实际年龄水平"
        if delta <= 3.0:
            return "存在轻度代谢-炎症负荷，建议生活方式干预"
        if delta <= 6.0:
            return "代谢-炎症负荷较明显，建议重点干预并复测"
        return "代谢-炎症负荷显著，建议结合临床检查"


# 八轴轴标识（供上层融合引擎引用）
AXIS_KEY = "metabolic_inflammatory"
AXIS_LABEL = "代谢-炎症轴"
