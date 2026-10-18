"""
multimodal.py — 多模态八轴倾向速判原型（P2）

借鉴 EyeAgent / VisionDoctor 的工具箱 + RAG 接地 + 自校正模式：
  - 把「舌色 / 苔腻 / 面色 / 体态」做成独立视觉工具
  - 每个工具输出置信度 + grounding 条文
  - axis_infer 聚合为 A-H 概率分布
  - self_check 在矛盾时触发二级复核

当前为原型：视觉模型用确定性规则/mock 模拟，真实落地时替换为
本地小模型或受控云端 API（audit 会拦截未授权外呼）。

用法：
  python -m healthlens_agent probe --image-desc "舌淡红、苔薄白、面色萎黄、体态乏力"
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass

from . import safety as sg


@dataclass
class VisualToolResult:
    tool: str
    finding: str
    confidence: float  # 0-1
    evidence: str  # grounding 条文


@dataclass
class MultimodalReport:
    axis_probs: dict[str, float]
    dominant_axis: str
    contradictions: list[str]
    safety_passed: bool
    safety_findings: list[dict]
    note: str


# ---------------------------------------------------------------------------
# 视觉工具箱（mock / 规则基线；真实模型替换此处）
# ---------------------------------------------------------------------------
_TONGUE_COLOR_RULES = [
    ("淡红", "B", 0.3, "《望诊遵经》：舌淡红为荣，气血和也。"),
    ("红", "B", 0.55, "《舌鉴辨正》：舌红者，热在营血。"),
    ("暗|紫", "C", 0.65, "《医林改错》：舌质紫暗，瘀血之象。"),
    ("淡白", "B", 0.55, "《中医诊断学》：淡白舌主气血两虚。"),
]

_TONGUE_COAT_RULES = [
    ("薄白", None, 0.2, "《中医诊断学》：薄白苔为正常或表证初起。"),
    ("厚腻", "C", 0.6, "《脾胃论》：苔厚腻者，湿浊内停。"),
    ("少苔|无苔", "B", 0.5, "《温热论》：舌无苔而干燥，胃阴不足。"),
]

_FACE_COLOR_RULES = [
    ("苍白", "B", 0.6, "《中医诊断学》：面色苍白，气血亏虚。"),
    ("萎黄", "B", 0.55, "《中医诊断学》：面色萎黄，脾胃虚弱。"),
    ("潮红", "F", 0.5, "《中医诊断学》：面色潮红，多为热象。"),
    ("青|暗", "C", 0.55, "《中医诊断学》：面色青暗，主瘀血或寒凝。"),
]

_BODY_POSTURE_RULES = [
    ("乏力|懒言", "B", 0.6, "《素问》：气虚则倦怠乏力。"),
    ("蜷缩|畏寒", "B", 0.55, "《伤寒论》：恶寒踡卧，阳气不足。"),
    ("躁动|不安", "G", 0.5, "《内经》：肝主疏泄，情志不遂则躁扰。"),
]


_ALL_RULES = (
    _TONGUE_COLOR_RULES + _TONGUE_COAT_RULES + _FACE_COLOR_RULES + _BODY_POSTURE_RULES
)


def _match_rule(
    desc: str, rules: list[tuple[str, str | None, float, str]]
) -> VisualToolResult | None:
    for pattern, axis, conf, evidence in rules:
        if re.search(pattern, desc):
            return VisualToolResult(
                tool="visual", finding=pattern, confidence=conf, evidence=evidence
            )
    return None


def tool_tongue_color(desc: str) -> VisualToolResult:
    return _match_rule(desc, _TONGUE_COLOR_RULES) or VisualToolResult(
        "tongue_color", "未识别", 0.0, "未匹配到舌色特征。"
    )


def tool_tongue_coat(desc: str) -> VisualToolResult:
    return _match_rule(desc, _TONGUE_COAT_RULES) or VisualToolResult(
        "tongue_coat", "未识别", 0.0, "未匹配到苔象特征。"
    )


def tool_face_color(desc: str) -> VisualToolResult:
    return _match_rule(desc, _FACE_COLOR_RULES) or VisualToolResult(
        "face_color", "未识别", 0.0, "未匹配到面色特征。"
    )


def tool_body_posture(desc: str) -> VisualToolResult:
    return _match_rule(desc, _BODY_POSTURE_RULES) or VisualToolResult(
        "body_posture", "未识别", 0.0, "未匹配到体态特征。"
    )


# ---------------------------------------------------------------------------
# axis_infer：聚合视觉结论 → 八轴概率分布
# ---------------------------------------------------------------------------
_AXIS_NAMES = {
    "A": "气化/自噬",
    "B": "气血-线粒体",
    "C": "络脉-清瘀",
    "D": "阴阳-昼夜",
    "E": "脏腑-神经内分泌",
    "F": "正邪-炎症",
    "G": "神-情志",
    "H": "先天-肾精",
}


def axis_infer(results: list[VisualToolResult]) -> tuple[dict[str, float], list[str]]:
    probs = {ax: 0.05 for ax in _AXIS_NAMES}
    contradictions = []

    for r in results:
        for pattern, axis, conf, evidence in _ALL_RULES:
            if evidence == r.evidence and axis:
                probs[axis] += conf * 0.4

    total = sum(probs.values())
    if total > 0:
        probs = {k: v / total for k, v in probs.items()}

    red_tongue = any("红" in r.finding for r in results)
    pale_face = any("苍白" in r.finding for r in results)
    if red_tongue and pale_face:
        contradictions.append("舌红（热象）与面色苍白（虚寒）并存，建议结合问诊复核。")

    return probs, contradictions


# ---------------------------------------------------------------------------
# 安全闸门 + 报告
# ---------------------------------------------------------------------------
def analyze(desc: str) -> MultimodalReport:
    results = [
        r
        for r in [
            tool_tongue_color(desc),
            tool_tongue_coat(desc),
            tool_face_color(desc),
            tool_body_posture(desc),
        ]
        if r.confidence > 0
    ]
    probs, contradictions = axis_infer(results)
    dominant = max(probs, key=probs.get)

    pre = sg.pre_gate(desc)
    return MultimodalReport(
        axis_probs={
            f"{k}({_AXIS_NAMES[k]})": round(v, 3) for k, v in sorted(probs.items())
        },
        dominant_axis=f"{dominant}({_AXIS_NAMES[dominant]})",
        contradictions=contradictions,
        safety_passed=pre.passed,
        safety_findings=[f.to_dict() for f in pre.findings],
        note="本结果为八轴倾向速判，非诊断；真实视觉模型替换工具箱内部规则后可用于 Demo。",
    )


def main():
    parser = argparse.ArgumentParser(description="HealthLens 多模态八轴倾向原型")
    parser.add_argument(
        "--image-desc", required=True, help="图像描述文本（模拟视觉模型输出）"
    )
    args = parser.parse_args()
    report = analyze(args.image_desc)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))


def demo():
    print("=== multimodal：多模态八轴倾向原型 ===\n")
    desc = "舌淡红、苔薄白、面色萎黄、体态乏力"
    report = analyze(desc)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    print(
        "\n[完成] 真实落地时把工具箱内规则替换为受控视觉模型，并接入 audit 监控外呼。"
    )
