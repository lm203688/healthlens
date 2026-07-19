"""慢病风险评估引擎
Phase 1: 基于循证医学指南的规则评分
Phase 2: 集成 ML 模型 (XGBoost/Cox 回归)

参考指南:
- 《中国心血管病风险评估和管理指南》(China-PAR 模型)
- 《中国2型糖尿病防治指南》糖尿病风险评分
- 《中国高血压防治指南》心血管风险分层
-代谢综合征: 中华医学会糖尿病学分会(CDS)标准
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from loguru import logger
from typing import Any


@dataclass
class RiskFactor:
    """风险因素"""
    name: str
    value: Any
    status: str  # "normal" | "borderline" | "high" | "danger"
    points: int = 0
    advice: str = ""


@dataclass
class RiskAssessmentResult:
    """风险评估结果"""
    risk_type: str              # 评估类型: ascvd / diabetes / hypertension / metabolic
    risk_level: str             # 风险等级: low / moderate / high / very_high
    risk_score: float           # 风险评分
    risk_probability: float     # 风险概率(百分比)
    risk_factors: list[RiskFactor] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    assessed_at: str = ""


class ASCVDRiskEngine:
    """动脉粥样硬化性心血管疾病(ASCVD)风险评估
    基于 China-PAR 模型简化版
    """

    # China-PAR 模型系数 (简化版)
    # 完整模型包含: 年龄、性别、腰围、TC、HDL-C、SBP、高血压治疗、吸烟、糖尿病、心血管病家族史、地区
    # 此处采用评分简化版

    def assess(self, age: int, gender: str, sbp: float, tc: float,
               hdl_c: float | None = None, ldl_c: float | None = None,
               is_smoker: bool = False, has_diabetes: bool = False,
               has_family_history: bool = False, waist: float | None = None,
               on_antihypertensive: bool = False) -> RiskAssessmentResult:
        """评估 10 年 ASCVD 风险"""

        factors: list[RiskFactor] = []
        score = 0

        # 年龄 (40-79 岁适用)
        if age >= 40:
            if gender == "male":
                if age >= 55:
                    score += 3
                    factors.append(RiskFactor("年龄", age, "high", 3, "年龄≥55岁，风险增加"))
                elif age >= 45:
                    score += 2
                    factors.append(RiskFactor("年龄", age, "borderline", 2, "年龄≥45岁"))
                else:
                    score += 1
                    factors.append(RiskFactor("年龄", age, "borderline", 1, "年龄≥40岁"))
            else:  # female
                if age >= 65:
                    score += 3
                    factors.append(RiskFactor("年龄", age, "high", 3, "年龄≥65岁，风险增加"))
                elif age >= 55:
                    score += 2
                    factors.append(RiskFactor("年龄", age, "borderline", 2, "年龄≥55岁"))
                else:
                    score += 1
                    factors.append(RiskFactor("年龄", age, "borderline", 1, "年龄≥40岁"))
        else:
            factors.append(RiskFactor("年龄", age, "normal", 0, "年龄<40岁，风险较低"))

        # 收缩压
        if sbp >= 160:
            score += 3
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "danger", 3, "血压≥160，需立即干预"))
        elif sbp >= 140:
            score += 2
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "high", 2, "高血压，需治疗"))
        elif sbp >= 130:
            score += 1
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "borderline", 1, "血压偏高，建议监测"))

            if on_antihypertensive:
                score += 1
                factors.append(RiskFactor("降压治疗", "是", "borderline", 1, "已用降压药，血压仍偏高"))
        else:
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "normal", 0, "血压正常"))

        # 总胆固醇 (mmol/L)
        if tc >= 6.2:
            score += 2
            factors.append(RiskFactor("总胆固醇", f"{tc} mmol/L", "high", 2, "TC≥6.2，高胆固醇血症"))
        elif tc >= 5.2:
            score += 1
            factors.append(RiskFactor("总胆固醇", f"{tc} mmol/L", "borderline", 1, "TC 边缘升高"))
        else:
            factors.append(RiskFactor("总胆固醇", f"{tc} mmol/L", "normal", 0, "TC 正常"))

        # HDL-C (保护因素)
        if hdl_c is not None:
            if hdl_c < 1.0:
                score += 1
                factors.append(RiskFactor("HDL-C", f"{hdl_c} mmol/L", "high", 1, "HDL-C 偏低，保护作用减弱"))
            elif hdl_c >= 1.5:
                score -= 1
                factors.append(RiskFactor("HDL-C", f"{hdl_c} mmol/L", "normal", -1, "HDL-C 较高，保护作用强"))

        # LDL-C
        if ldl_c is not None:
            if ldl_c >= 4.1:
                score += 2
                factors.append(RiskFactor("LDL-C", f"{ldl_c} mmol/L", "high", 2, "LDL-C 极高，需药物治疗"))
            elif ldl_c >= 3.4:
                score += 1
                factors.append(RiskFactor("LDL-C", f"{ldl_c} mmol/L", "borderline", 1, "LDL-C 偏高"))

        # 吸烟
        if is_smoker:
            if gender == "male":
                score += 2
                factors.append(RiskFactor("吸烟", "是", "high", 2, "男性吸烟显著增加心血管风险"))
            else:
                score += 1
                factors.append(RiskFactor("吸烟", "是", "high", 1, "吸烟增加心血管风险"))

        # 糖尿病
        if has_diabetes:
            score += 2
            factors.append(RiskFactor("糖尿病", "是", "danger", 2, "糖尿病为 ASCVD 等危症"))

        # 家族史
        if has_family_history:
            score += 1
            factors.append(RiskFactor("心血管病家族史", "是", "borderline", 1, "一级亲属早发心血管病史"))

        # 腰围
        if waist is not None:
            if gender == "male" and waist >= 90:
                score += 1
                factors.append(RiskFactor("腰围", f"{waist} cm", "high", 1, "男性腹型肥胖(≥90cm)"))
            elif gender == "female" and waist >= 85:
                score += 1
                factors.append(RiskFactor("腰围", f"{waist} cm", "high", 1, "女性腹型肥胖(≥85cm)"))

        # 确定风险等级
        # 简化的 10 年风险概率映射 (非线性)
        if score <= 3:
            risk_level = "low"
            probability = min(5.0, score * 1.2)
            recommendations = [
                "保持健康生活方式: 均衡饮食、规律运动、戒烟限酒",
                "每 2-3 年复查一次血脂、血压",
                "维持理想体重(BMI 18.5-24)",
            ]
        elif score <= 6:
            risk_level = "moderate"
            probability = 5.0 + (score - 3) * 3.0
            recommendations = [
                "加强生活方式干预: 低盐低脂饮食、每周≥150分钟中等强度运动",
                "每年复查血脂、血压、血糖",
                "考虑使用他汀类药物(LDL-C≥3.4 时)",
                "监测血压，目标<130/80 mmHg",
            ]
        elif score <= 10:
            risk_level = "high"
            probability = 14.0 + (score - 6) * 4.0
            recommendations = [
                "积极控制危险因素: 降压、降脂、降糖",
                "他汀类药物治疗(LDL-C 目标<2.6 mmol/L)",
                "阿司匹林一级预防(评估出血风险后)",
                "每 6 个月复查，建议心内科就诊",
            ]
        else:
            risk_level = "very_high"
            probability = min(30.0 + (score - 10) * 3.0, 50.0)
            recommendations = [
                "心血管专科就诊，制定个体化治疗方案",
                "强化降脂: LDL-C 目标<1.8 mmol/L",
                "抗血小板治疗(阿司匹林/氯吡格雷)",
                "控制血压<130/80，血糖达标",
                "每 3 个月复查，必要时冠脉 CTA 筛查",
            ]

        return RiskAssessmentResult(
            risk_type="ascvd",
            risk_level=risk_level,
            risk_score=float(score),
            risk_probability=round(probability, 1),
            risk_factors=factors,
            recommendations=recommendations,
            references=["中国心血管病风险评估和管理指南(China-PAR)", "中国成人血脂异常防治指南"],
            assessed_at=datetime.now().isoformat(),
        )


class DiabetesRiskEngine:
    """2型糖尿病风险评估
    基于中国糖尿病风险评分(CDRS)简化版
    """

    def assess(self, age: int, gender: str, bmi: float, sbp: float,
               waist: float, family_history: bool = False) -> RiskAssessmentResult:
        """评估 2 型糖尿病风险"""

        factors: list[RiskFactor] = []
        score = 0

        # 年龄
        if age >= 50:
            score += 4
            factors.append(RiskFactor("年龄", age, "high", 4, "年龄≥50岁"))
        elif age >= 40:
            score += 3
            factors.append(RiskFactor("年龄", age, "borderline", 3, "年龄≥40岁"))
        elif age >= 30:
            score += 1
            factors.append(RiskFactor("年龄", age, "borderline", 1, "年龄≥30岁"))

        # BMI
        if bmi >= 28:
            score += 5
            factors.append(RiskFactor("BMI", f"{bmi}", "danger", 5, "肥胖(BMI≥28)"))
        elif bmi >= 24:
            score += 3
            factors.append(RiskFactor("BMI", f"{bmi}", "high", 3, "超重(BMI≥24)"))

        # 腰围 (腹型肥胖)
        if gender == "male":
            if waist >= 95:
                score += 4
                factors.append(RiskFactor("腰围", f"{waist} cm", "danger", 4, "男性重度腹型肥胖"))
            elif waist >= 90:
                score += 2
                factors.append(RiskFactor("腰围", f"{waist} cm", "high", 2, "男性腹型肥胖"))
        else:
            if waist >= 90:
                score += 4
                factors.append(RiskFactor("腰围", f"{waist} cm", "danger", 4, "女性重度腹型肥胖"))
            elif waist >= 85:
                score += 2
                factors.append(RiskFactor("腰围", f"{waist} cm", "high", 2, "女性腹型肥胖"))

        # 收缩压
        if sbp >= 140:
            score += 3
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "high", 3, "高血压"))
        elif sbp >= 130:
            score += 1
            factors.append(RiskFactor("收缩压", f"{sbp} mmHg", "borderline", 1, "血压偏高"))

        # 家族史
        if family_history:
            score += 3
            factors.append(RiskFactor("糖尿病家族史", "是", "high", 3, "一级亲属糖尿病史"))

        # 确定风险等级
        if score < 5:
            risk_level = "low"
            probability = min(2.0 + score * 0.8, 5.0)
            recommendations = [
                "保持健康体重(BMI<24)",
                "每周≥150分钟中等强度运动",
                "均衡饮食，减少精制糖摄入",
                "每 3 年检测空腹血糖",
            ]
        elif score <= 10:
            risk_level = "moderate"
            probability = 5.0 + (score - 4) * 2.5
            recommendations = [
                "强化生活方式干预(饮食+运动)",
                "每年检测空腹血糖+糖化血红蛋白",
                "必要时行 OGTT(口服葡萄糖耐量试验)",
                "控制体重，目标 BMI<24",
            ]
        elif score <= 15:
            risk_level = "high"
            probability = 20.0 + (score - 10) * 3.0
            recommendations = [
                "内分泌科就诊，行 OGTT + HbA1c 检查",
                "严格饮食控制(低 GI 饮食)",
                "每周≥150分钟有氧运动+抗阻训练",
                "考虑药物干预(二甲双胍)",
                "每 6 个月复查",
            ]
        else:
            risk_level = "very_high"
            probability = min(35.0 + (score - 15) * 2.5, 55.0)
            recommendations = [
                "立即内分泌科就诊，全面评估",
                "OGTT + HbA1c + 胰岛功能检查",
                "药物干预(二甲双胍/GLP-1 受体激动剂)",
                "严格控制饮食和运动",
                "监测并发症(眼底/肾脏/神经)",
            ]

        return RiskAssessmentResult(
            risk_type="diabetes",
            risk_level=risk_level,
            risk_score=float(score),
            risk_probability=round(probability, 1),
            risk_factors=factors,
            recommendations=recommendations,
            references=["中国2型糖尿病防治指南", "中国糖尿病风险评分(CDRS)"],
            assessed_at=datetime.now().isoformat(),
        )


class MetabolicSyndromeEngine:
    """代谢综合征评估
    基于 CDS(中华医学会糖尿病学分会)标准
    """

    # CDS 标准: 符合以下 3 项或以上即可诊断
    # 1. 腹型肥胖: 腰围男≥90cm, 女≥85cm
    # 2. 高血糖: FPG≥6.1 mmol/L 或已治疗
    # 3. 高血压: ≥130/85 mmHg 或已治疗
    # 4. 空腹 TG≥1.7 mmol/L
    # 5. 空腹 HDL-C<1.04(男) / <1.30(女)

    def assess(self, gender: str, waist: float, fpg: float | None = None,
               sbp: float = 120, dbp: float = 80, tg: float | None = None,
               hdl_c: float | None = None,
               on_glucose_med: bool = False, on_bp_med: bool = False) -> RiskAssessmentResult:
        """评估代谢综合征"""

        factors: list[RiskFactor] = []
        criteria_met = 0

        # 1. 腹型肥胖
        if gender == "male":
            if waist >= 90:
                criteria_met += 1
                factors.append(RiskFactor("腹型肥胖", f"腰围 {waist} cm", "high", 1, "男性腰围≥90cm"))
            else:
                factors.append(RiskFactor("腹型肥胖", f"腰围 {waist} cm", "normal", 0, "腰围正常"))
        else:
            if waist >= 85:
                criteria_met += 1
                factors.append(RiskFactor("腹型肥胖", f"腰围 {waist} cm", "high", 1, "女性腰围≥85cm"))
            else:
                factors.append(RiskFactor("腹型肥胖", f"腰围 {waist} cm", "normal", 0, "腰围正常"))

        # 2. 高血糖
        if fpg is not None:
            if fpg >= 6.1 or on_glucose_med:
                criteria_met += 1
                factors.append(RiskFactor("高血糖", f"FPG {fpg} mmol/L", "high", 1, "空腹血糖≥6.1"))
            else:
                factors.append(RiskFactor("高血糖", f"FPG {fpg} mmol/L", "normal", 0, "血糖正常"))

        # 3. 高血压
        if sbp >= 130 or dbp >= 85 or on_bp_med:
            criteria_met += 1
            factors.append(RiskFactor("高血压", f"{sbp}/{dbp} mmHg", "high", 1, "血压≥130/85"))
        else:
            factors.append(RiskFactor("高血压", f"{sbp}/{dbp} mmHg", "normal", 0, "血压正常"))

        # 4. 高甘油三酯
        if tg is not None:
            if tg >= 1.7:
                criteria_met += 1
                factors.append(RiskFactor("高甘油三酯", f"TG {tg} mmol/L", "high", 1, "TG≥1.7"))
            else:
                factors.append(RiskFactor("高甘油三酯", f"TG {tg} mmol/L", "normal", 0, "TG 正常"))

        # 5. 低 HDL-C
        if hdl_c is not None:
            if gender == "male" and hdl_c < 1.04:
                criteria_met += 1
                factors.append(RiskFactor("低 HDL-C", f"{hdl_c} mmol/L", "high", 1, "男性 HDL-C<1.04"))
            elif gender == "female" and hdl_c < 1.30:
                criteria_met += 1
                factors.append(RiskFactor("低 HDL-C", f"{hdl_c} mmol/L", "high", 1, "女性 HDL-C<1.30"))
            else:
                factors.append(RiskFactor("低 HDL-C", f"{hdl_c} mmol/L", "normal", 0, "HDL-C 正常"))

        # 确定结果
        is_metabolic_syndrome = criteria_met >= 3
        if is_metabolic_syndrome:
            if criteria_met >= 4:
                risk_level = "very_high"
                recommendations = [
                    "诊断为代谢综合征，需综合干预",
                    "严格控制饮食(低盐低脂低糖)",
                    "每周≥150分钟运动+抗阻训练",
                    "药物干预: 降糖/降压/降脂联合治疗",
                    "每 3 个月复查，监测心血管事件",
                ]
            else:
                risk_level = "high"
                recommendations = [
                    "诊断为代谢综合征",
                    "强化生活方式干预(饮食+运动)",
                    "针对性药物治疗(根据异常指标)",
                    "每 6 个月复查",
                ]
        elif criteria_met == 2:
            risk_level = "moderate"
            recommendations = [
                "代谢综合征前期，有 2 项异常",
                "加强生活方式干预",
                "每年复查",
            ]
        else:
            risk_level = "low"
            recommendations = [
                "代谢指标基本正常",
                "保持健康生活方式",
                "每 2 年复查",
            ]

        return RiskAssessmentResult(
            risk_type="metabolic_syndrome",
            risk_level=risk_level,
            risk_score=float(criteria_met),
            risk_probability=100.0 if is_metabolic_syndrome else criteria_met * 20.0,
            risk_factors=factors,
            recommendations=recommendations,
            references=["中华医学会糖尿病学分会代谢综合征标准"],
            assessed_at=datetime.now().isoformat(),
        )


class RiskAssessmentEngine:
    """慢病风险评估总引擎"""

    def __init__(self):
        self.ascvd = ASCVDRiskEngine()
        self.diabetes = DiabetesRiskEngine()
        self.metabolic = MetabolicSyndromeEngine()

    def assess_all(self, profile: dict) -> dict[str, RiskAssessmentResult]:
        """根据用户健康档案进行全量风险评估

        profile 字段:
            age, gender, bmi, waist, sbp, dbp, tc, tg, hdl_c, ldl_c, fpg
            is_smoker, has_diabetes, has_family_history (心血管)
            on_antihypertensive, on_glucose_med
        """
        results: dict[str, RiskAssessmentResult] = {}

        age = profile.get("age", 0)
        gender = profile.get("gender", "male")
        sbp = profile.get("sbp", 120)
        tc = profile.get("tc", 0)
        bmi = profile.get("bmi", 22)
        waist = profile.get("waist", 80)

        try:
            # ASCVD 评估 (40 岁以上)
            if age >= 40:
                results["ascvd"] = self.ascvd.assess(
                    age=age, gender=gender, sbp=sbp, tc=tc,
                    hdl_c=profile.get("hdl_c"),
                    ldl_c=profile.get("ldl_c"),
                    is_smoker=profile.get("is_smoker", False),
                    has_diabetes=profile.get("has_diabetes", False),
                    has_family_history=profile.get("has_family_history", False),
                    waist=waist,
                    on_antihypertensive=profile.get("on_antihypertensive", False),
                )

            # 糖尿病风险评估
            results["diabetes"] = self.diabetes.assess(
                age=age, gender=gender, bmi=bmi, sbp=sbp, waist=waist,
                family_history=profile.get("diabetes_family_history", False),
            )

            # 代谢综合征评估
            results["metabolic_syndrome"] = self.metabolic.assess(
                gender=gender, waist=waist,
                fpg=profile.get("fpg"),
                sbp=sbp, dbp=profile.get("dbp", 80),
                tg=profile.get("tg"),
                hdl_c=profile.get("hdl_c"),
                on_glucose_med=profile.get("on_glucose_med", False),
                on_bp_med=profile.get("on_antihypertensive", False),
            )

            logger.info(f"Risk assessment completed: {len(results)} assessments for {gender}, age {age}")

        except Exception as e:
            logger.error(f"Risk assessment failed: {e}")

        return results

    def get_overall_risk_level(self, results: dict[str, RiskAssessmentResult]) -> tuple[str, float]:
        """根据多项评估结果，给出总体风险等级"""
        if not results:
            return "unknown", 0.0

        level_weights = {"low": 1, "moderate": 2, "high": 3, "very_high": 4}
        max_level = 0
        max_probability = 0.0

        for result in results.values():
            level_num = level_weights.get(result.risk_level, 1)
            if level_num > max_level:
                max_level = level_num
            if result.risk_probability > max_probability:
                max_probability = result.risk_probability

        overall_level = {1: "low", 2: "moderate", 3: "high", 4: "very_high"}.get(max_level, "low")
        return overall_level, max_probability
