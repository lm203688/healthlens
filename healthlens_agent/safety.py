"""
safety.py — HealthLens 安全闸门（借鉴 MedAssist 前置红牌 + LabGuard typed guard IR）

设计要点（来自 GOAI 榜单借鉴）：
- MedAssist-Agent（赛道一）：在任何 Agent 运行前先跑规则扫描，命中医学急症即拦截并给急救指引，分级（无/中/高）。
- LabGuard（赛道一同源）：自然语言规则 → 类型化可执行 IR → 运行时监控器，可量化"不安全事件率"。

本模块把 HealthLens 的「八轴红线 + 去医疗化 + 医学急症红牌 + 证据分级」形式化为
typed guard IR（GuardRule），并提供两道运行时监控器：
  - pre_gate(user_input)        生成前：拦截医学急症、越界诉求
  - post_gate(generated, cited)  生成后：拦截去医疗化违反、红线击穿、证据断链

无第三方依赖，可直接 `python -m healthlens_agent safety` 运行演示。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class GuardCategory(StrEnum):
    RED_FLAG = "red_flag"  # 医学急症红牌（前置拦截）
    DEMEDICALIZE = "demedicalize"  # 去医疗化红线（不得诊断/开方/替代就医）
    AXIS_REDLINE = "axis_redline"  # 八轴稳态红线（不得承诺治愈/逆转）
    EVIDENCE_GRADE = "evidence_grade"  # 证据分级（L1-L3 不可越级断言）


class Severity(StrEnum):
    HALT = "halt"  # 直接拦截，禁止生成/输出
    WARN = "warn"  # 放行但加警示横幅
    BLOCK = "block"  # 阻断该条输出，要求改写


@dataclass
class GuardRule:
    """typed guard IR 的最小单元：一条可编译、可审计、可量化的约束。"""

    id: str
    category: GuardCategory
    severity: Severity
    description: str
    matcher: Callable[[str], bool]
    message: str
    suggestion: str = ""

    def check(self, text: str) -> bool:
        return bool(self.matcher(text))


@dataclass
class Finding:
    rule_id: str
    category: GuardCategory
    severity: Severity
    snippet: str
    message: str
    suggestion: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "snippet": self.snippet[:120],
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class GateResult:
    passed: bool
    level: str = "none"  # none / caution / halt
    findings: list[Finding] = field(default_factory=list)

    @property
    def unsafe_event(self) -> bool:
        """LabGuard 式量化指标：本次是否出现不安全事件（任一 HALT/BLOCK 命中）。"""
        return any(f.severity in (Severity.HALT, Severity.BLOCK) for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "level": self.level,
            "unsafe_event": self.unsafe_event,
            "findings": [f.to_dict() for f in self.findings],
        }


# ---------------------------------------------------------------------------
# 规则库（typed guard IR 实例）—— 可随八轴理论扩展、可基准测试
# ---------------------------------------------------------------------------

_RED_FLAG_PATTERNS = [
    ("胸痛", "可能为心肺急症"),
    ("呼吸困难", "可能为呼吸/心肺急症"),
    (
        "卒中|中风|半身不遂|口眼歪斜|半边.{0,3}麻木|言语不清|说话含糊",
        "可能为脑血管意外",
    ),
    ("大出血|呕血|咯血|便血量大", "可能为消化道/呼吸道大出血"),
    ("意识丧失|昏迷|晕厥", "可能为神经系统急症"),
    ("自杀|自残|不想活", "可能为心理急症"),
    ("抽搐|惊厥", "可能为神经/代谢急症"),
]

_DEMEDICALIZE_PATTERNS = [
    ("确诊你得了|你患有|你得了.{0,6}病", "不得给出诊断结论"),
    ("我建议你服用.{0,8}药|给你开.{0,6}方|处方如下", "不得开具处方/替代就医"),
    ("治愈你的|彻底根治|保证治好", "不得承诺治愈/根治"),
    ("代替医生|替代医院|无需就医", "不得替代专业医疗"),
]

_AXIS_REDLINE_PATTERNS = [
    ("逆转衰老|永生|长生", "八轴不得擅自承诺逆转先天/衰老"),
    ("100%有效|包好|绝对安全", "不得作绝对化疗效承诺"),
]


def _make_pattern_finder(patterns):
    compiled = [(re.compile(p, re.IGNORECASE), desc) for p, desc in patterns]

    def finder(text: str) -> str | None:
        for rx, desc in compiled:
            m = rx.search(text)
            if m:
                return m.group(0)
        return None

    return finder


_redflag_find = _make_pattern_finder(_RED_FLAG_PATTERNS)
_demed_find = _make_pattern_finder(_DEMEDICALIZE_PATTERNS)
_axis_find = _make_pattern_finder(_AXIS_REDLINE_PATTERNS)


def build_rules() -> list[GuardRule]:
    rules: list[GuardRule] = []

    # 1) 医学急症红牌（前置，HALT）
    rules.append(
        GuardRule(
            id="RF-001",
            category=GuardCategory.RED_FLAG,
            severity=Severity.HALT,
            description="识别医学急症关键词，生成前拦截并给急救指引",
            matcher=lambda t: _redflag_find(t) is not None,
            message="检测到可能的医学急症信号，已停止生成并建议立即就医。",
            suggestion="请立即联系急救（如 120）或前往最近急诊；本工具不处理急症。",
        )
    )

    # 2) 去医疗化红线（生成后，BLOCK）
    for i, (pat, desc) in enumerate(_DEMEDICALIZE_PATTERNS):
        rules.append(
            GuardRule(
                id=f"DM-{i + 1:03d}",
                category=GuardCategory.DEMEDICALIZE,
                severity=Severity.BLOCK,
                description=desc,
                matcher=lambda t, p=pat: re.search(p, t, re.IGNORECASE) is not None,
                message="输出违反去医疗化红线（不得诊断/开方/承诺治愈/替代就医）。",
                suggestion="改写为非诊断、非处方式的稳态调理建议，并附免责声明。",
            )
        )

    # 3) 八轴稳态红线（生成后，BLOCK）
    for i, (pat, desc) in enumerate(_AXIS_REDLINE_PATTERNS):
        rules.append(
            GuardRule(
                id=f"AX-{i + 1:03d}",
                category=GuardCategory.AXIS_REDLINE,
                severity=Severity.BLOCK,
                description=desc,
                matcher=lambda t, p=pat: re.search(p, t, re.IGNORECASE) is not None,
                message="输出击穿八轴稳态红线（不得作绝对化/越界承诺）。",
                suggestion="改写为概率化、个体化、非承诺式的表述。",
            )
        )

    return rules


RULES = build_rules()


# ---------------------------------------------------------------------------
# 两道运行时监控器
# ---------------------------------------------------------------------------


def pre_gate(user_input: str) -> GateResult:
    """生成前闸门：拦截医学急症等高危诉求（MedAssist 前置红牌）。"""
    findings: list[Finding] = []
    for rule in RULES:
        if rule.category != GuardCategory.RED_FLAG:
            continue
        if rule.check(user_input):
            snippet = _redflag_find(user_input) or user_input
            findings.append(
                Finding(
                    rule.id,
                    rule.category,
                    rule.severity,
                    snippet,
                    rule.message,
                    rule.suggestion,
                )
            )
    if findings:
        return GateResult(passed=False, level="halt", findings=findings)
    return GateResult(passed=True, level="none", findings=[])


def post_gate(generated: str, cited_evidence: list[str] | None = None) -> GateResult:
    """生成后闸门：拦截去医疗化违反、八轴红线击穿、证据断链。"""
    findings: list[Finding] = []
    for rule in RULES:
        if rule.category == GuardCategory.RED_FLAG:
            continue
        if rule.check(generated):
            snippet = _demed_find(generated) or _axis_find(generated) or generated
            findings.append(
                Finding(
                    rule.id,
                    rule.category,
                    rule.severity,
                    snippet,
                    rule.message,
                    rule.suggestion,
                )
            )
    # 证据断链检查：声明有证据但引用为空 → EVIDENCE_GRADE 警告
    if cited_evidence is not None and len(cited_evidence) == 0 and "依据" in generated:
        findings.append(
            Finding(
                "EG-001",
                GuardCategory.EVIDENCE_GRADE,
                Severity.WARN,
                generated[:80],
                "声明有依据但引用为空，证据链断裂。",
                "补充古籍条目/基因位点/案例 ID 之一作为溯源。",
            )
        )
    level = (
        "halt"
        if any(f.severity == Severity.HALT for f in findings)
        else ("caution" if findings else "none")
    )
    passed = not any(f.severity in (Severity.HALT, Severity.BLOCK) for f in findings)
    return GateResult(passed=passed, level=level, findings=findings)


def demo():
    print("=== safety：前置红牌 + 后置闸门演示 ===\n")
    cases = [
        ("用户说：我最近总是胸痛伴随呼吸困难", "pre", None),
        ("生成：根据八轴分析，建议你服用六味地黄丸，处方如下：...", "post", []),
        ("生成：本方案可100%有效逆转你的衰老", "post", ["case-024"]),
        ("用户说：帮我看看最近容易疲劳怎么调理", "pre", None),
        (
            "生成：从A轴（气化）看，建议早睡并晨间光照，依据见古籍《黄帝内经》",
            "post",
            ["黄帝内经/素问"],
        ),
    ]
    for text, stage, cited in cases:
        r = pre_gate(text) if stage == "pre" else post_gate(text, cited)
        tag = "生成前闸门" if stage == "pre" else "生成后闸门"
        print(f"[{tag}] {text}")
        print(f"  -> passed={r.passed} level={r.level} unsafe_event={r.unsafe_event}")
        for f in r.findings:
            print(
                f"     ! {f.rule_id}/{f.category.value}/{f.severity.value}: {f.message}"
            )
        print()

    sample = [
        pre_gate("我胸痛"),
        post_gate("给你开药方", []),
        post_gate("建议早睡", ["黄帝内经"]),
        pre_gate("最近疲劳"),
    ]
    unsafe = sum(1 for s in sample if s.unsafe_event)
    print(
        f"不安全事件率（演示样本）: {unsafe}/{len(sample)} = {unsafe / len(sample):.0%}"
    )
