"""西医健康评估引擎（AI 辅助健康评估 + 风险分层 + 趋势预警）
============================================================
定位重构（2026-11-04，红线重构）：
  · 本引擎**不再承担"诊断"**——它只做「AI 辅助健康评估 + 风险分层 +
    趋势预警」，即对检验指标异常进行分级解读并给出就医建议。
  · "诊断"作为独立门控模块（见 app/core/diagnosis_gate.py），默认
    inactive，不激活、不注册、不产生疾病结论。
  · 输出统一表述为「评估/发现/风险分层」，避免"疑似疾病/诊断"措辞。

诚实边界：
  · 本引擎是规则驱动的**探索性/研究性**工具，置信度 0.65 为启发式
    权重，非临床验证值；不宣称"已验证诊断"。
  · 任何"指标异常 → 疾病名"的映射仅为**风险提示**，须由持牌医疗
    机构复核确认，不构成诊断结论。

Phase 1: 基于规则引擎的健康评估（指标异常→风险分层映射）
Phase 2: 集成医学大模型（评估增强，仍非诊断）
"""
from decimal import Decimal
from dataclasses import dataclass, field


@dataclass
class DiagnosisFinding:
    name: str                    # 风险/异常名称（不再称"疾病名"）
    icd_code: str               # ICD-11 编码（仅供医疗机构参考映射）
    severity: str               # mild / moderate / severe
    confidence: float           # 0-1 启发式权重（非临床验证）
    evidence: list[str]         # 依据的指标
    recommendations: list[str]  # 建议（就医/生活方式）
    kind: str = "risk_finding"  # risk_finding（非 diagnosis）


class WesternDiagnosisEngine:
    """基于规则引擎的西医健康评估（AI 辅助）— Phase 1

    本引擎仅做健康评估与风险分层，不产生医疗结论。
    """

    # 常见指标异常 → 疑似疾病映射
    # key: loinc_code, value: (疾病名, icd_code, 严重度, 建议列表)
    DIAGNOSIS_RULES = {
        "2345-7": {  # 血糖
            "high": {
                "name": "空腹血糖偏高",
                "icd_code": "5A11",
                "severity": "moderate",
                "recommendations": [
                    "建议复查空腹血糖及糖化血红蛋白(HbA1c)",
                    "控制碳水化合物摄入，增加运动",
                    "如持续偏高，建议内分泌科就诊",
                ],
            },
            "low": {
                "name": "低血糖倾向",
                "icd_code": "5A14",
                "severity": "mild",
                "recommendations": ["规律饮食，避免长时间空腹", "随身携带糖果"],
            },
        },
        "2093-3": {  # 总胆固醇
            "high": {
                "name": "高胆固醇血症",
                "icd_code": "5C70",
                "severity": "moderate",
                "recommendations": [
                    "减少饱和脂肪和反式脂肪摄入",
                    "增加膳食纤维，规律有氧运动",
                    "如持续偏高，考虑他汀类药物治疗",
                ],
            },
        },
        "2085-9": {  # 甘油三酯
            "high": {
                "name": "高甘油三酯血症",
                "icd_code": "5C71",
                "severity": "mild",
                "recommendations": [
                    "控制酒精和高糖食物摄入",
                    "增加omega-3脂肪酸摄入",
                    "规律运动，控制体重",
                ],
            },
        },
        "2571-8": {  # ALT 谷丙转氨酶
            "high": {
                "name": "肝功能异常(ALT升高)",
                "icd_code": "BA00",
                "severity": "moderate",
                "recommendations": [
                    "排除酒精、药物性肝损伤",
                    "建议查乙肝五项、丙肝抗体",
                    "如持续升高需消化内科就诊",
                ],
            },
        },
        "785-6": {  # WBC 白细胞
            "high": {
                "name": "白细胞增多",
                "icd_code": "BA20",
                "severity": "mild",
                "recommendations": [
                    "可能存在感染或炎症",
                    "建议结合症状判断",
                    "1-2周后复查",
                ],
            },
            "low": {
                "name": "白细胞减少",
                "icd_code": "BA30",
                "severity": "moderate",
                "recommendations": [
                    "建议血液科就诊",
                    "排除药物、感染等继发因素",
                ],
            },
        },
        "718-7": {  # 血红蛋白
            "low": {
                "name": "贫血",
                "icd_code": "3A00",
                "severity": "moderate",
                "recommendations": [
                    "建议查铁代谢、叶酸、B12",
                    "适当补充含铁丰富的食物",
                    "排除慢性失血可能",
                ],
            },
            "high": {
                "name": "血红蛋白增多",
                "icd_code": "3A01",
                "severity": "mild",
                "recommendations": [
                    "排除脱水因素",
                    "如持续偏高建议血液科就诊",
                ],
            },
        },
        "6299-1": {  # 肌酐
            "high": {
                "name": "肾功能异常(肌酐升高)",
                "icd_code": "GB60",
                "severity": "moderate",
                "recommendations": [
                    "建议查肾小球滤过率(eGFR)",
                    "控制蛋白质摄入",
                    "肾内科就诊明确病因",
                ],
            },
        },
    }

    def assess_from_observations(self, observations: list[dict]) -> list[DiagnosisFinding]:
        """基于健康指标异常检测结果生成风险分层评估（非诊断）"""
        findings = []

        for obs in observations:
            loinc = obs.get("loinc_code")
            value = obs.get("value_numeric")
            low = obs.get("reference_range_low")
            high = obs.get("reference_range_high")
            name = obs.get("loinc_name", "Unknown")

            if not loinc or value is None or loinc not in self.DIAGNOSIS_RULES:
                continue

            rules = self.DIAGNOSIS_RULES[loinc]

            if high is not None and value > high:
                rule = rules.get("high")
                if rule:
                    findings.append(DiagnosisFinding(
                        name=rule["name"],
                        icd_code=rule["icd_code"],
                        severity=rule["severity"],
                        confidence=0.65,  # 规则引擎启发式权重（非临床验证）
                        evidence=[f"{name}: {value} (参考上限 {high})"],
                        recommendations=rule["recommendations"],
                        kind="risk_finding",
                    ))
            elif low is not None and value < low:
                rule = rules.get("low")
                if rule:
                    findings.append(DiagnosisFinding(
                        name=rule["name"],
                        icd_code=rule["icd_code"],
                        severity=rule["severity"],
                        confidence=0.65,
                        evidence=[f"{name}: {value} (参考下限 {low})"],
                        recommendations=rule["recommendations"],
                        kind="risk_finding",
                    ))

        return findings

    # 兼容别名（旧调用方仍可用，但语义为"评估"）
    def diagnose_from_observations(self, observations: list[dict]) -> list[DiagnosisFinding]:
        """兼容别名：等同 assess_from_observations（语义已改为评估）。"""
        return self.assess_from_observations(observations)

    async def assess(self, user_id: str, observations: list[dict]) -> list[DiagnosisFinding]:
        """异步接口 - 基于规则引擎的健康评估（非诊断）"""
        return self.assess_from_observations(observations)

    # 兼容别名
    async def diagnose(self, user_id: str, observations: list[dict]) -> list[DiagnosisFinding]:
        """兼容别名：等同 assess（语义已改为评估）。"""
        return self.assess_from_observations(observations)
