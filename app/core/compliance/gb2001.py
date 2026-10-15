"""GB/T 20001.10-2014 条款映射模块

将国标条款映射到 HealthLens 的 wellness 服务文档结构，
提供条款级检查能力。

定位：结构化文档合规参考，非法律/监管合规声明。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 配置路径：本地项目根在 healthlens/（parents[3]），容器内 app 挂载到 /app/app
# 但项目根在 /app（parents[3] 指向 /app，config 不在那里）。做 fallback 兼容两种布局。
# 生产容器已把 /opt/healthlens/config 通过 docker cp 放到 /app/config/，fallback 后
# 直接命中 parents[3]；若镜像 rebuild 后未挂 config，则回退 parents[2]/config/
# （app 目录内），由 docker compose 挂载保证存在。
_GB2001_PATH_CANDIDATES = [
    Path(__file__).resolve().parents[3] / "config" / "national_standards.json",
    Path(__file__).resolve().parents[2] / "config" / "national_standards.json",
]
CONFIG_PATH = next((p for p in _GB2001_PATH_CANDIDATES if p.exists()), _GB2001_PATH_CANDIDATES[0])

# 缓存：standard_id → 标准 dict（含 clauses / disclaimer 等）
_standards_cache: dict[str, dict[str, Any]] = {}
_config_cache: dict[str, Any] | None = None

# mandatory / optional 扣分（0-100 分制）
MANDATORY_PENALTY = 20
OPTIONAL_PENALTY = 5


class NationalStandardError(RuntimeError):
    """国标闸门错误。fail-closed：宁可拒答，不放行违规输出。"""


@dataclass
class ClauseResult:
    """单条款检查结果。"""
    clause_id: str
    title: str
    priority: str  # mandatory / optional
    passed: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class StandardGateResult:
    """国标闸门总体结果。"""
    standard_id: str
    standard_title: str
    passed: bool
    score: int  # 0-100
    clause_results: list[ClauseResult]
    mandatory_passed: int
    mandatory_total: int
    optional_passed: int
    optional_total: int
    critical_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = ""


# ── 配置加载 ────────────────────────────────────────────────────

def _load_config() -> dict[str, Any]:
    """加载并校验整个国标配置文件。

    fail-closed：文件缺失或格式错误时抛 NationalStandardError。
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if not CONFIG_PATH.exists():
        raise NationalStandardError(f"国标配置文件不存在: {CONFIG_PATH}")

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise NationalStandardError(f"国标配置文件格式错误: {e}") from e
    except OSError as e:
        raise NationalStandardError(f"国标配置文件读取失败: {e}") from e

    if not isinstance(data, dict) or not isinstance(data.get("standards"), list) or not data["standards"]:
        raise NationalStandardError("国标配置文件缺少 'standards' 数组")

    _config_cache = data
    return data


def load_standards() -> list[dict]:
    """加载所有国标列表。"""
    cfg = _load_config()
    return cfg["standards"]


def get_standard(standard_id: str) -> dict[str, Any]:
    """按 ID 获取单个国标配置。"""
    if standard_id in _standards_cache:
        return _standards_cache[standard_id]
    cfg = _load_config()
    for s in cfg["standards"]:
        if s.get("id") == standard_id:
            _standards_cache[standard_id] = s
            return s
    raise NationalStandardError(f"未知国标: {standard_id}")


def reload_config() -> None:
    """清空缓存，下次访问重新加载磁盘。测试或热更新时用。"""
    global _config_cache
    _config_cache = None
    _standards_cache.clear()


def get_global_disclaimer() -> str:
    """获取顶层免责声明。"""
    cfg = _load_config()
    return cfg.get("disclaimer", "")


# ── 条款检查 ────────────────────────────────────────────────────

def _extract_keywords(clause: dict) -> list[str]:
    """从条款中抽取用于文本匹配的关键词。

    优先用 title；requirement 也参与匹配（作为关键词补充）。
    """
    keywords: list[str] = []
    for key in ("title", "requirement"):
        v = clause.get(key)
        if v and isinstance(v, str) and v.strip():
            keywords.append(v.strip())
    return keywords


def check_clause(doc_text: str, clause: dict) -> ClauseResult:
    """检查单条款：在文档中查找条款要求的关键词/结构。

    fail-closed：条款字段缺失 → 判失败。
    """
    clause_id = clause.get("id", "?")
    title = clause.get("title", "")
    priority = clause.get("priority", "mandatory")
    method = clause.get("check_method", "text_presence")
    requirement = clause.get("requirement", "")

    if not doc_text:
        return ClauseResult(
            clause_id=clause_id,
            title=title,
            priority=priority,
            passed=False,
            message="文档为空，条款无法满足",
            details=[f"clause={clause_id}", "doc_text is empty"],
        )

    text_lower = doc_text.lower()

    if method == "text_presence":
        # 在文档中查找条款 ID 或标题/需求关键词
        id_hit = clause_id.lower() in text_lower
        keywords = _extract_keywords(clause)
        keyword_hits = [kw for kw in keywords if kw.lower() in text_lower]

        # 至少命中 ID 或一个关键词即视为通过
        if id_hit or keyword_hits:
            return ClauseResult(
                clause_id=clause_id,
                title=title,
                priority=priority,
                passed=True,
                message=f"条款命中：id={id_hit}, keywords={keyword_hits}",
                details=[f"clause_id_in_doc={id_hit}", f"keywords_hit={keyword_hits}"],
            )
        return ClauseResult(
            clause_id=clause_id,
            title=title,
            priority=priority,
            passed=False,
            message=f"条款未命中：{title}（requirement={requirement}）",
            details=[f"clause_id_in_doc=False", f"keywords_hit=[]", f"requirement={requirement}"],
        )

    if method == "structure_check":
        # 检查文档是否有对应章节结构（标题或编号）
        heading_patterns = [
            f"#{len(str(clause_id).split('.')[0])} {clause_id}",
            f"## {clause_id}",
            f"### {clause_id}",
            f"{clause_id} ",
            f"{clause_id}\n",
        ]
        for pat in heading_patterns:
            if pat.lower() in text_lower:
                return ClauseResult(
                    clause_id=clause_id,
                    title=title,
                    priority=priority,
                    passed=True,
                    message=f"章节结构命中：{pat}",
                    details=[f"pattern={pat}"],
                )
        return ClauseResult(
            clause_id=clause_id,
            title=title,
            priority=priority,
            passed=False,
            message=f"章节结构缺失：{title}",
            details=[f"missing_heading={clause_id}"],
        )

    if method == "reference_check":
        # 检查引用文件是否完整（要求文档中出现「GB/T」或「GB/」等引用标识）
        ref_markers = ["GB/T", "GB/", "ISO", "IEC", "JJF", "参考文献", "引用文件"]
        hits = [m for m in ref_markers if m.lower() in text_lower]
        if hits:
            return ClauseResult(
                clause_id=clause_id,
                title=title,
                priority=priority,
                passed=True,
                message=f"引用标识命中：{hits}",
                details=[f"ref_markers={hits}"],
            )
        return ClauseResult(
            clause_id=clause_id,
            title=title,
            priority=priority,
            passed=False,
            message="未找到规范性引用文件",
            details=["missing_reference_markers"],
        )

    # 未知 check_method → fail-closed，判失败
    return ClauseResult(
        clause_id=clause_id,
        title=title,
        priority=priority,
        passed=False,
        message=f"未知检查方法：{method}（fail-closed）",
        details=[f"check_method={method}"],
    )


# ── 文档闸门 ────────────────────────────────────────────────────

def check_document(doc_text: str, standard_id: str = "GB/T 20001.10-2014") -> StandardGateResult:
    """对文档运行国标闸门。

    - mandatory 条款不通过 → passed=False，score -= 20
    - optional  条款不通过 → passed 不变，score -= 5
    - fail-closed：闸门自身异常 → 返回 passed=False（不静默降级）
    """
    fallback_disclaimer = (
        "本国标闸门为健康管理服务文档提供结构化参考，"
        "非医疗诊断标准，不构成法律或监管合规声明。"
    )
    global_score = ""
    try:
        global_score = get_global_disclaimer()
    except Exception:  # noqa: BLE001
        global_score = fallback_disclaimer

    try:
        standard = get_standard(standard_id)
        clauses = standard.get("clauses", [])
        std_title = standard.get("title", standard_id)
        std_disclaimer = standard.get("disclaimer") or global_score

        clause_results: list[ClauseResult] = []
        mandatory_total = 0
        mandatory_passed = 0
        optional_total = 0
        optional_passed = 0
        critical_issues: list[str] = []
        warnings: list[str] = []

        for clause in clauses:
            r = check_clause(doc_text or "", clause)
            clause_results.append(r)
            is_mandatory = (clause.get("priority") or "mandatory") == "mandatory"
            if is_mandatory:
                mandatory_total += 1
                if r.passed:
                    mandatory_passed += 1
                else:
                    critical_issues.append(f"[{clause.get('id')}] {r.message}")
            else:
                optional_total += 1
                if r.passed:
                    optional_passed += 1
                else:
                    warnings.append(f"[{clause.get('id')}] {r.message}")

        # 计算总分
        score = 100
        score -= (mandatory_total - mandatory_passed) * MANDATORY_PENALTY
        score -= (optional_total - optional_passed) * OPTIONAL_PENALTY
        score = max(0, min(100, score))

        # 判定：只要有 mandatory 不通过即 fail
        passed = (mandatory_total == 0) or (mandatory_passed == mandatory_total)

        return StandardGateResult(
            standard_id=standard_id,
            standard_title=std_title,
            passed=passed,
            score=score,
            clause_results=clause_results,
            mandatory_passed=mandatory_passed,
            mandatory_total=mandatory_total,
            optional_passed=optional_passed,
            optional_total=optional_total,
            critical_issues=critical_issues,
            warnings=warnings,
            disclaimer=std_disclaimer,
        )

    except NationalStandardError as e:
        # 配置/标准不存在 → fail-closed
        logger.error(f"国标闸门配置错误（fail-closed）: {e}")
        return StandardGateResult(
            standard_id=standard_id,
            standard_title=standard_id,
            passed=False,
            score=0,
            clause_results=[],
            mandatory_passed=0,
            mandatory_total=0,
            optional_passed=0,
            optional_total=0,
            critical_issues=[f"[gate_config_error] {e}"],
            warnings=[],
            disclaimer=global_score,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"国标闸门内部异常（fail-closed）: {e}")
        return StandardGateResult(
            standard_id=standard_id,
            standard_title=standard_id,
            passed=False,
            score=0,
            clause_results=[],
            mandatory_passed=0,
            mandatory_total=0,
            optional_passed=0,
            optional_total=0,
            critical_issues=[f"[gate_internal_error] {type(e).__name__}: {e}"],
            warnings=[],
            disclaimer=global_score,
        )


def check_document_on_file(filepath: str | Path) -> StandardGateResult:
    """对文件运行国标闸门。"""
    p = Path(filepath)
    if not p.exists():
        raise NationalStandardError(f"文档文件不存在: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise NationalStandardError(f"文档读取失败: {e}") from e
    return check_document(text)


__all__ = [
    "CONFIG_PATH",
    "NationalStandardError",
    "ClauseResult",
    "StandardGateResult",
    "load_standards",
    "get_standard",
    "reload_config",
    "get_global_disclaimer",
    "check_clause",
    "check_document",
    "check_document_on_file",
    "MANDATORY_PENALTY",
    "OPTIONAL_PENALTY",
]
