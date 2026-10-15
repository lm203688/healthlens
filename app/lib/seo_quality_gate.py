"""SEO 内容发布质量闸门（M14）

在 SEO 内容发布到生产环境前进行多维度质量校验：
1. **合规闸门**：检查是否包含医疗宣称/诊断暗示/治疗承诺
2. **质量闸门**：检查字数、结构完整性、Schema 标记完整性
3. **重复闸门**：检查与已有内容的语义重复度
4. **急救闸门**：检查内容是否包含可能导致用户延误就医的表述

设计原则：
- fail-closed：任何检查失败都不放行
- 非阻塞警告：非关键问题仅记录，不阻断发布
- 与 ClaimsEngine 共享敏感词库
- 检查结果可审计
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

# ── 合规检查 ────────────────────────────────────────────────────

# 医疗宣称禁用词（出现在 SEO 内容中视为违规）
MEDICAL_CLAIM_PATTERNS = [
    "治疗", "治愈", "根治", "药到病除", "包治", "100%有效",
    "特效", "根治", "保证有效", "无效退款",
    "诊断", "确诊", "临床诊断",
    "处方", "开药", "处方药",
    "患者", "病人", "病例",
]

# 急救相关词（SEO 内容不应建议用户自行处理急症）
EMERGENCY_MISGUIDE_PATTERNS = [
    "不需要去医院", "不用看医生", "在家就能治",
    "不用担心", "没什么大事", "自己会好",
    "不用着急", "可以等等看",
]

# 过度承诺词
OVER_PROMISE_PATTERNS = [
    "最快", "最强", "最好", "第一", "唯一",
    "保证", "一定", "绝对", "必定",
]

# 占位/未完成标记（批量生成器留下的草稿不得发布）
PLACEHOLDER_PATTERNS = [
    "正在生成中", "待补充", "占位", "lorem ipsum",
    "示例内容", "TODO", "FIXME", "XXX", "略", "此处省略",
]

# 免责声明语境词：医疗宣称词若出现在**同一句**内包含这些词，视为
# 免责声明式引用（如"不构成医疗诊断依据"），不算医疗宣称。
# 注意：判断范围必须是"命中词所在的句子"，不是固定字符窗口——
# 用窗口会让页面别处的免责声明掩盖任意位置的违规宣称（fail-open）。
DISCLAIMER_CONTEXT_TERMS = [
    "不构成", "不提供", "不是", "非医疗", "不能替代", "不替代",
    "请咨询", "建议咨询", "局限", "免责", "仅供参考", "养生参考",
]

# 句子边界：中文标点 + HTML 块级标签闭合处
_SENTENCE_BOUNDARY_RE = re.compile(r"[。！？；\n<]|</?(?:p|div|h[1-6]|li|blockquote)[\s>]", re.I)


class GateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class GateCheckResult:
    """单项检查结果"""
    check_name: str
    status: GateStatus
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class QualityGateResult:
    """质量闸门总体结果"""
    passed: bool
    checks: list[GateCheckResult]
    score: int  # 0-100 综合质量分
    critical_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── 内容检查函数 ─────────────────────────────────────────────────

def _extract_text(html: str) -> str:
    """从 HTML 提取纯文本（去标签）

    ``html`` 可能为 ``None`` 或非字符串（调用方传空字段）。此时返回空串，
    让后续检查以"内容缺失"判定失败，而不是在这里抛 TypeError。
    """
    if not html or not isinstance(html, (str, bytes)):
        return ""
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    return re.sub(r"<[^>]+>", " ", html).strip()


def _sentences(text: str) -> list[str]:
    """按中文标点与块级标签切分句子，用于声明语境的精确定位。"""
    if not text:
        return []
    parts = _SENTENCE_BOUNDARY_RE.split(text)
    return [p.strip() for p in parts if p and p.strip()]


def _check_placeholder(text: str) -> GateCheckResult:
    """占位内容检查：批量生成器留下的未完成标记不得发布。

    这是 `POST /pages/generate` 产出的草稿页（"正在生成中..."）的核心拦截点——
    该端点生成的页面 `word_count=0`，修复前可被一键发布到公开站点。
    """
    hits: list[str] = []
    text_lower = text.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.lower() in text_lower:
            hits.append(pattern)
    if hits:
        return GateCheckResult(
            check_name="placeholder",
            status=GateStatus.FAIL,
            message=f"包含未完成/占位内容，不得发布：{'、'.join(hits)}",
            details=hits,
        )
    return GateCheckResult(
        check_name="placeholder",
        status=GateStatus.PASS,
        message="无占位内容",
    )


def _check_word_count(text: str) -> GateCheckResult:
    """字数检查：SEO 内容应 ≥300 字，优质内容 ≥800 字"""
    char_count = len(re.sub(r"\s", "", text))
    if char_count < 150:
        return GateCheckResult(
            check_name="word_count",
            status=GateStatus.FAIL,
            message=f"内容过短（{char_count} 字），SEO 内容应至少 300 字",
        )
    if char_count < 300:
        return GateCheckResult(
            check_name="word_count",
            status=GateStatus.WARN,
            message=f"内容偏短（{char_count} 字），建议扩充至 300 字以上",
        )
    if char_count < 800:
        return GateCheckResult(
            check_name="word_count",
            status=GateStatus.WARN,
            message=f"内容一般（{char_count} 字），建议扩充至 800 字以上以提升 SEO 质量",
        )
    return GateCheckResult(
        check_name="word_count",
        status=GateStatus.PASS,
        message=f"字数充足（{char_count} 字）",
    )


def _check_structure(html: str) -> GateCheckResult:
    """结构完整性检查：必须有 H1、H2、meta description、canonical"""
    issues: list[str] = []
    if not re.search(r"<h1[\s>]", html, re.I):
        issues.append("缺少 H1 标题")
    if not re.search(r"<h2[\s>]", html, re.I):
        issues.append("缺少 H2 小节标题")
    if not re.search(r'<meta[^>]*name="description"', html, re.I):
        issues.append("缺少 meta description")
    if not re.search(r'rel="canonical"', html, re.I):
        issues.append("缺少 canonical URL")

    if issues:
        return GateCheckResult(
            check_name="structure",
            status=GateStatus.FAIL,
            message="结构不完整：" + "、".join(issues),
            details=issues,
        )
    return GateCheckResult(
        check_name="structure",
        status=GateStatus.PASS,
        message="结构完整",
    )


def _check_schema(html: str) -> GateCheckResult:
    """Schema.org 标记检查：至少需要 Article + FAQPage"""
    issues: list[str] = []
    if not re.search(r'"@type"\s*:\s*"Article"', html):
        issues.append("缺少 Article Schema")
    if not re.search(r'"@type"\s*:\s*"FAQPage"', html):
        issues.append("缺少 FAQPage Schema")
    if not re.search(r'"@type"\s*:\s*"MedicalWebPage"', html):
        issues.append("缺少 MedicalWebPage Schema")

    if issues:
        return GateCheckResult(
            check_name="schema",
            status=GateStatus.WARN,
            message="Schema 标记不完整：" + "、".join(issues),
            details=issues,
        )
    return GateCheckResult(
        check_name="schema",
        status=GateStatus.PASS,
        message="Schema 标记完整",
    )


def _check_medical_claims(text: str) -> GateCheckResult:
    """医疗宣称检查：内容不应包含诊断/治疗/治愈等宣称。

    判定粒度是**命中词所在的句子**，不是固定字符窗口。

    此前的实现用 ``±50/80`` 字符窗口判断免责声明语境，结果是：页面里只要
    任何位置有一句免责声明，**整页任意位置**的医疗宣称都会被那个窗口扫到
    免责词而放行（fail-open）。实测复现：正文写"本方案可以确诊并根治糖尿病"，
    而同页 filler 含"不构成医疗建议"，闸门判 PASS——医疗宣称被完全绕过。

    改为按句子切分后，只对命中词所在的同一句判定语境，
    "不构成医疗诊断依据"（句内含免责词）放行，
    "本方案可以确诊并根治糖尿病"（句内无免责词）拦截。
    """
    hits: list[str] = []
    sentences = _sentences(text)

    for pattern in MEDICAL_CLAIM_PATTERNS:
        pattern_lower = pattern.lower()
        for sentence in sentences:
            if pattern_lower not in sentence.lower():
                continue
            # 同一句内出现免责声明语境词 → 视为声明式引用，放行该词
            if any(dc in sentence for dc in DISCLAIMER_CONTEXT_TERMS):
                continue
            hits.append(pattern)
            break  # 同一 pattern 只需命中一次

    if hits:
        return GateCheckResult(
            check_name="medical_claims",
            status=GateStatus.FAIL,
            message=f"包含医疗宣称：{'、'.join(hits)}",
            details=hits,
        )
    return GateCheckResult(
        check_name="medical_claims",
        status=GateStatus.PASS,
        message="无医疗宣称",
    )


def _check_emergency_misguide(text: str) -> GateCheckResult:
    """急救误导检查：内容不应建议用户延误就医"""
    hits: list[str] = []
    text_lower = text.lower()
    for pattern in EMERGENCY_MISGUIDE_PATTERNS:
        if pattern in text_lower:
            hits.append(pattern)

    if hits:
        return GateCheckResult(
            check_name="emergency_misguide",
            status=GateStatus.FAIL,
            message=f"可能误导用户延误就医：{'、'.join(hits)}",
            details=hits,
        )
    return GateCheckResult(
        check_name="emergency_misguide",
        status=GateStatus.PASS,
        message="无急救误导风险",
    )


def _check_over_promise(text: str) -> GateCheckResult:
    """过度承诺检查：内容不应使用绝对化用语"""
    hits: list[str] = []
    text_lower = text.lower()
    for pattern in OVER_PROMISE_PATTERNS:
        if pattern in text_lower:
            hits.append(pattern)

    if hits:
        return GateCheckResult(
            check_name="over_promise",
            status=GateStatus.WARN,
            message=f"包含过度承诺用语：{'、'.join(hits)}",
            details=hits,
        )
    return GateCheckResult(
        check_name="over_promise",
        status=GateStatus.PASS,
        message="无过度承诺",
    )


def _check_limitation_statement(html: str) -> GateCheckResult:
    """局限性声明检查：必须包含免责声明/局限性声明"""
    if re.search(r"(局限性|免责|不构成.*建议|仅供参考|不构成.*诊断)", html):
        return GateCheckResult(
            check_name="limitation",
            status=GateStatus.PASS,
            message="包含局限性声明",
        )
    return GateCheckResult(
        check_name="limitation",
        status=GateStatus.FAIL,
        message="缺少局限性声明/免责声明",
    )


def _check_duplicate(html: str, existing_slugs: set[str] | None = None, slug: str = "") -> GateCheckResult:
    """重复检查：检查 slug 是否已存在"""
    if slug and existing_slugs and slug in existing_slugs:
        return GateCheckResult(
            check_name="duplicate",
            status=GateStatus.FAIL,
            message=f"slug 重复：{slug} 已存在",
        )
    return GateCheckResult(
        check_name="duplicate",
        status=GateStatus.PASS,
        message="无重复",
    )


# ── 主入口 ───────────────────────────────────────────────────────

def run_quality_gate(
    html: str,
    slug: str = "",
    existing_slugs: set[str] | None = None,
) -> QualityGateResult:
    """运行 SEO 内容质量闸门

    Args:
        html: 待发布的 HTML 内容
        slug: 内容 slug（用于重复检查）
        existing_slugs: 已有 slug 集合（用于重复检查）

    Returns:
        QualityGateResult 包含所有检查结果和综合评分
    """
    # 闸门 fail-closed：自身任何未预期异常都判"不可发布"，绝不放行。
    # 闸门坏掉比内容不合格更危险——它会静默变成"永不拦截"。
    try:
        return _run_quality_gate_inner(html, slug, existing_slugs)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Quality gate internal error for slug={slug}: {exc}")
        return QualityGateResult(
            passed=False,
            checks=[GateCheckResult(
                check_name="gate_internal_error",
                status=GateStatus.FAIL,
                message=f"质量闸门执行异常：{exc}",
                details=[type(exc).__name__],
            )],
            score=0,
            critical_issues=[f"[gate_internal_error] 质量闸门执行异常：{exc}"],
            warnings=[],
        )


def _run_quality_gate_inner(
    html: str,
    slug: str,
    existing_slugs: set[str] | None,
) -> QualityGateResult:
    """闸门的实际执行体（被 ``run_quality_gate`` 的 fail-closed 包装保护）。"""
    text = _extract_text(html)
    # HTML 结构类检查需要原始 HTML；content_html 为空/None 时给空串，
    # 让结构检查以"缺失"判失败，而不是抛异常。
    html_for_structure = html if isinstance(html, str) else ""
    checks: list[GateCheckResult] = []

    # 运行所有检查
    checks.append(_check_placeholder(text))
    checks.append(_check_word_count(text))
    checks.append(_check_structure(html_for_structure))
    checks.append(_check_schema(html_for_structure))
    checks.append(_check_medical_claims(text))
    checks.append(_check_emergency_misguide(text))
    checks.append(_check_over_promise(text))
    checks.append(_check_limitation_statement(html_for_structure))
    checks.append(_check_duplicate(html_for_structure, existing_slugs, slug))

    # 计算综合评分
    score = 100
    critical_issues: list[str] = []
    warnings: list[str] = []

    for check in checks:
        if check.status == GateStatus.FAIL:
            score -= 20
            critical_issues.append(f"[{check.check_name}] {check.message}")
        elif check.status == GateStatus.WARN:
            score -= 5
            warnings.append(f"[{check.check_name}] {check.message}")

    score = max(0, min(100, score))

    # 判定是否通过
    passed = not critical_issues

    if not passed:
        logger.warning(
            f"Quality gate FAILED: slug={slug}, score={score}, "
            f"critical={len(critical_issues)}, warnings={len(warnings)}"
        )
    else:
        logger.info(f"Quality gate PASSED: slug={slug}, score={score}")

    return QualityGateResult(
        passed=passed,
        checks=checks,
        score=score,
        critical_issues=critical_issues,
        warnings=warnings,
    )


def run_quality_gate_on_file(
    filepath: str | Path,
    existing_slugs: set[str] | None = None,
) -> QualityGateResult:
    """对文件运行质量闸门

    Args:
        filepath: HTML 文件路径
        existing_slugs: 已有 slug 集合

    Returns:
        QualityGateResult
    """
    filepath = Path(filepath)
    html = filepath.read_text(encoding="utf-8")
    slug = filepath.stem
    return run_quality_gate(html, slug, existing_slugs)
