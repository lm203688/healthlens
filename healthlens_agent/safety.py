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
    PRIVACY = "privacy"  # 隐私红线（输出不得含 PII；借鉴 llm-healthcare-threat-modeling 输出 PII 清洗）
    BIAS = "bias"  # 偏见红线（不得对群体作一刀切歧视性断言；深层偏见仍需 LLM judge）


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
    (
        r"一次\s*(吃了?|服用了?|吞了?)\s*\d+\s*(片|粒|颗|瓶)|过量服[用食药]|误服过量|吞了整瓶",
        "可能为急性药物过量/中毒",
    ),
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

# PII 输出红线（借鉴 llm-healthcare-threat-modeling 第四阶段「输出 PII 清洗」）：
# 移动手机号 / 18 位身份证 / 邮箱。命中即 BLOCK，且提供 scrub_pii 做打码清洗。
_PII_PATTERNS = [
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "手机号"),
    (r"(?<!\d)\d{17}[\dXx](?!\d)", "身份证号"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "邮箱"),
]

_BIAS_PATTERNS = [
    (
        r"老年人?普遍不适合|老人都(不适合|不宜|不用)|女性天生不适合|男性(不需要|不适合)调理|年轻人不需要调理",
        "不得对人口学群体作一刀切断言",
    ),
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
_bias_find = _make_pattern_finder(_BIAS_PATTERNS)
_pii_compiled = [(re.compile(p), name) for p, name in _PII_PATTERNS]


def find_pii(text: str) -> list[tuple[str, str]]:
    """返回命中的 PII 列表 [(原文, 类型)]，供清洗与审计使用。"""
    hits: list[tuple[str, str]] = []
    for rx, name in _pii_compiled:
        for m in rx.finditer(text):
            hits.append((m.group(0), name))
    return hits


def scrub_pii(text: str) -> tuple[str, int]:
    """输出 PII 清洗器：将手机号/身份证/邮箱打码为掩码。返回 (清洗后文本, 清洗条数)。

    打码保留首尾少量字符以便人工复核，其余以 * 代替（PII 最小化原则）。
    """
    count = 0
    out = text
    for rx, name in _pii_compiled:
        def _mask(m: re.Match) -> str:
            nonlocal count
            count += 1
            s = m.group(0)
            if name == "邮箱":
                local, _, dom = s.partition("@")
                head = local[:2]
                return f"{head}***@{dom}"
            keep = 3 if name == "手机号" else 4
            return s[:keep] + "*" * max(len(s) - keep - 2, 3) + s[-2:]
        out = rx.sub(_mask, out)
    return out, count


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

    # 4) 隐私红线（生成后，BLOCK）：输出不得携带 PII（PI-001）
    rules.append(
        GuardRule(
            id="PI-001",
            category=GuardCategory.PRIVACY,
            severity=Severity.BLOCK,
            description="输出不得包含手机号/身份证号/邮箱等个人身份信息",
            matcher=lambda t: bool(find_pii(t)),
            message="输出包含个人身份信息（PII），违反隐私红线。",
            suggestion="用 scrub_pii() 打码后再输出；确需记录请走用户授权的加密存储通道。",
        )
    )

    # 5) 偏见红线（生成后，BLOCK）：群体一刀切断言（BX-001；深层偏见仍需 LLM judge）
    for i, (pat, desc) in enumerate(_BIAS_PATTERNS):
        rules.append(
            GuardRule(
                id=f"BX-{i + 1:03d}",
                category=GuardCategory.BIAS,
                severity=Severity.BLOCK,
                description=desc,
                matcher=lambda t, p=pat: re.search(p, t, re.IGNORECASE) is not None,
                message="输出对人口学群体作一刀切断言，违反公平性红线。",
                suggestion="改写为个体化评估表述，不做群体性概括。",
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
    """生成后闸门：拦截去医疗化违反、八轴红线击穿、证据断链、PII 泄漏、群体一刀切。"""
    findings: list[Finding] = []
    for rule in RULES:
        if rule.category == GuardCategory.RED_FLAG:
            continue
        if rule.check(generated):
            snippet = (
                _demed_find(generated)
                or _axis_find(generated)
                or _bias_find(generated)
                or (find_pii(generated)[0][0] if find_pii(generated) else None)
                or generated
            )
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
    # 证据断链检查：声明有依据但引用为空 → EVIDENCE_GRADE 警告
    # EG-001 触发词扩展：除「依据」外，覆盖「研究显示/研究表明/文献记载/临床证实」类
    # 无出处断言（红队 H-OUT-02 缺口修复）。
    _claim_rx = re.compile(r"研究显示|研究表明|研究证明|文献记载|临床证实|临床证明")
    has_claim = "依据" in generated or bool(_claim_rx.search(generated))
    if cited_evidence is not None and len(cited_evidence) == 0 and has_claim:
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


# ---------------------------------------------------------------------------
# 深层偏见判定接入（DAS 式 LLM-judge；需配 HL_JUDGE_*，否则诚实 skipped）
# ---------------------------------------------------------------------------
def deep_bias_check(answer: str) -> dict:
    """生成后置深层偏见判定（DAS 式 LLM-judge 接入点）。

    委托 healthlens_agent.bias_judge.judge_answer 对单条已生成回答做公平性判定。
    - 未配置 HL_JUDGE_* 环境变量 -> 返回 {"available": False, "label": "skipped"}，
      绝不伪装已评测（延续本仓诚实原则）。
    - 配置后（ECS /opt/healthlens/.env 加 HL_JUDGE_BASE_URL/API_KEY/MODEL）即自动激活，
      可对微妙统计性歧视/群体一刀切做深度识别，弥补 BX-001 确定性规则盲区。
    """
    try:
        from .bias_judge import judge_answer
    except ImportError:
        from healthlens_agent.bias_judge import judge_answer
    return judge_answer(answer)
