"""国标 2.0 闸门

集成 GB/T 20001.10-2014 条款映射，提供统一的闸门接口。
与 claims_engine / seo_quality_gate 并列，构成三重合规防线。

设计原则：
- fail-closed：任何异常都返回 passed=False，不静默降级
- 全部输出带 disclaimer，明确 wellness 边界
- 纯文本匹配，不依赖 NLP，结果可审计
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.compliance.gb2001 import (
    ClauseResult,
    StandardGateResult,
    check_document,
    get_standard,
    load_standards,
)


@dataclass
class GateChainResult:
    """多重闸门链式检查结果。"""
    passed: bool
    checks: list[dict] = field(default_factory=list)  # 每个闸门的检查结果
    total_score: int = 100
    critical_issues: list[str] = field(default_factory=list)


async def run_national_standard_gate(
    doc_text: str,
    jurisdiction: str = "cn",
    standard_id: str = "GB/T 20001.10-2014",
) -> dict:
    """运行国标闸门，返回检查结果。

    Args:
        doc_text: 待检查的文档文本
        jurisdiction: 法域（当前仅 cn 使用国标）
        standard_id: 国标编号（默认 GB/T 20001.10-2014）

    Returns:
        检查结果字典，结构见项目规格。
    """
    # fail-closed：闸门自身异常都返回 passed=False，不抛出
    try:
        result: StandardGateResult = check_document(doc_text or "", standard_id)
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "not_clinical": True,
            "standard_id": standard_id,
            "passed": False,
            "score": 0,
            "mandatory_passed": 0,
            "mandatory_total": 0,
            "optional_passed": 0,
            "optional_total": 0,
            "clause_results": [],
            "critical_issues": [f"[gate_internal_error] {type(e).__name__}: {e}"],
            "warnings": [],
            "disclaimer": "本国标闸门为健康管理服务文档提供结构化参考，非医疗诊断标准，不构成法律或监管合规声明。",
        }

    return {
        "success": True,
        "not_clinical": True,
        "standard_id": result.standard_id,
        "passed": result.passed,
        "score": result.score,
        "mandatory_passed": result.mandatory_passed,
        "mandatory_total": result.mandatory_total,
        "optional_passed": result.optional_passed,
        "optional_total": result.optional_total,
        "clause_results": [
            {
                "clause_id": cr.clause_id,
                "title": cr.title,
                "priority": cr.priority,
                "passed": cr.passed,
                "message": cr.message,
            }
            for cr in result.clause_results
        ],
        "critical_issues": result.critical_issues,
        "warnings": result.warnings,
        "disclaimer": result.disclaimer,
    }


def list_available_standards() -> list[dict]:
    """列出可用的国标。"""
    standards = load_standards()
    result: list[dict] = []
    for s in standards:
        clauses = s.get("clauses", [])
        mandatory = sum(1 for c in clauses if (c.get("priority") or "mandatory") == "mandatory")
        optional = len(clauses) - mandatory
        result.append({
            "id": s.get("id"),
            "title": s.get("title"),
            "scope": s.get("scope"),
            "clause_count": len(clauses),
            "mandatory_count": mandatory,
            "optional_count": optional,
            "disclaimer": s.get("disclaimer"),
        })
    return result


def get_standard_detail(standard_id: str) -> dict:
    """获取国标详情（含条款列表）。"""
    s = get_standard(standard_id)
    return {
        "id": s.get("id"),
        "title": s.get("title"),
        "scope": s.get("scope"),
        "clauses": s.get("clauses", []),
        "disclaimer": s.get("disclaimer"),
    }


def list_clauses(standard_id: str) -> list[dict]:
    """列出指定国标的条款。"""
    s = get_standard(standard_id)
    return s.get("clauses", [])


def build_compliance_report() -> dict:
    """构建国标闸门合规报告摘要。

    不针对具体文档，而是概述闸门能力与免责。
    """
    standards = load_standards()
    return {
        "not_clinical": True,
        "version": standards[0].get("id") if standards else "unknown",
        "standard_count": len(standards),
        "standards": [
            {
                "id": s.get("id"),
                "title": s.get("title"),
                "clause_count": len(s.get("clauses", [])),
            }
            for s in standards
        ],
        "disclaimer": (
            "本国标闸门为健康管理服务文档提供结构化参考，"
            "非医疗诊断标准，不构成法律或监管合规声明。"
        ),
    }


__all__ = [
    "GateChainResult",
    "run_national_standard_gate",
    "list_available_standards",
    "get_standard_detail",
    "list_clauses",
    "build_compliance_report",
]
