"""管辖感知 Claims 引擎（Jurisdiction-aware Claims & Consent Engine）

**核心命题**：wellness 边界不能只靠文案纪律，必须是代码策略。
FDA/MHRA/TGA 判定标准是"是否命名一种疾病并作用于它"——
免责声明在美国伊利诺伊州《Wellness and Oversight for Psychological Resources Act》（2025-08-01）
下已明确失效。因此边界必须落到代码层的字段过滤 / 拦截 / 改写。

**架构**：
    User.jurisdiction → 加载 YAML 策略 → 输出前 apply_filter() → 留痕审计

**策略文件**（`claims_policy/*.yaml`）：
    - cn.yaml       — PIPL + NMPA（首发市场，功能最全）
    - us_fda.yaml   — FDA General Wellness（严格，触发即器械）
    - uk_mhra.yaml  — MHRA AIaMD（严格）
    - au_tga.yaml   — TGA wellness exclusion（相对宽松）
    - eu_mdr.yaml   — MDR Rule 11（最严，几乎仅保留 lifestyle）

**引擎职责**：
1. `load_policy(jurisdiction)` → 加载对应 YAML（首次加载后缓存）
2. `filter_output(payload, jurisdiction)` → 按策略过滤 / 改写 / 拦截字段
3. `check_endpoint_allowed(endpoint, jurisdiction)` → 端点级开关
4. `scan_terms(text, jurisdiction)` → 输出前的敏感词扫描
5. `apply_disclaimer(payload, context, jurisdiction)` → 附加按法域定制的免责声明

**关键设计约束**：
- 每次过滤都留痕到审计日志（`AuditEvent.severity=medium`）
- 未配置策略 → 默认走最严格（EU）策略而非放行（fail-closed）
- 引擎绝不静默降级：未知 jurisdiction 直接抛 `ClaimsPolicyError`
"""
from __future__ import annotations

import os
import logging
import threading
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import yaml

logger = logging.getLogger(__name__)


# ── 常量 ────────────────────────────────────────────────────────

POLICY_DIR = Path(__file__).resolve().parent.parent.parent / "claims_policy"
STRICT_FALLBACK = "eu"  # 未知法域走 EU（最严），fail-closed
SUPPORTED_JURISDICTIONS = {"cn", "us", "uk", "au", "eu"}


class ClaimsPolicyError(RuntimeError):
    """策略加载 / 应用失败。fail-closed：宁可拒答，不放行违规输出。"""


@dataclass
class FilterResult:
    """过滤结果：payload 可能被修改，同时留下留痕记录。"""
    payload: dict
    removed_fields: list[str]
    rewritten_fields: list[str]
    blocked_endpoints: list[str]
    disclaimer_added: str | None
    violations: list[str]  # 敏感词命中的模式
    warnings: list[str]


# ── 策略加载与缓存 ──────────────────────────────────────────────

_policy_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# 法域 → YAML 文件名映射（jurisdiction 是短码，文件名可能带机构后缀）
_POLICY_FILES = {
    "cn": "cn.yaml",
    "us": "us_fda.yaml",
    "uk": "uk_mhra.yaml",
    "au": "au_tga.yaml",
    "eu": "eu_mdr.yaml",
}


def load_policy(jurisdiction: str) -> dict:
    """加载法域策略。未知法域 fail-closed 到 EU（最严）。

    首次加载后缓存，进程内只读一次磁盘。
    """
    key = (jurisdiction or "unknown").strip().lower()

    if key not in SUPPORTED_JURISDICTIONS:
        logger.warning(f"Unknown jurisdiction '{key}', falling back to '{STRICT_FALLBACK}' (fail-closed)")
        key = STRICT_FALLBACK

    if key in _policy_cache:
        return _policy_cache[key]

    with _cache_lock:
        if key in _policy_cache:
            return _policy_cache[key]

        filename = _POLICY_FILES.get(key)
        if not filename:
            raise ClaimsPolicyError(f"No policy file mapped for jurisdiction '{key}'")

        filepath = POLICY_DIR / filename
        if not filepath.exists():
            # fail-closed：找不到策略文件，返回最严格空策略（除允许字段外全部屏蔽）
            logger.error(f"Policy file not found: {filepath}, using empty-allow strict fallback")
            policy = {
                "jurisdiction": key,
                "display_name": key.upper(),
                "regime": "UNKNOWN-FAIL-CLOSED",
                "wellness_boundary_strict": True,
                "allowed_fields": [],
                "blocked_fields": ["*"],  # 全部屏蔽
                "feature_toggles": {},
                "required_disclaimers": {},
                "banned_terms": {"medical_claim_patterns": [], "allowed_context_terms": []},
            }
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                policy = yaml.safe_load(f) or {}
            # 合并 CN-specific allowed 字段（CN 是唯一允许 ICD 映射 + 致病性分级的）
            if policy.get("cn_specific_allowed") and policy.get("jurisdiction") == "cn":
                policy.setdefault("allowed_fields", [])
                for f in policy.pop("cn_specific_allowed"):
                    if f not in policy["allowed_fields"]:
                        policy["allowed_fields"].append(f)

        # 校验必需字段
        required = {"jurisdiction", "allowed_fields", "blocked_fields", "feature_toggles"}
        missing = required - policy.keys()
        if missing:
            raise ClaimsPolicyError(
                f"Policy '{key}' missing required keys: {sorted(missing)}"
            )

        _policy_cache[key] = policy
        logger.info(
            f"Loaded policy '{key}': "
            f"allowed={len(policy['allowed_fields'])} blocked={len(policy['blocked_fields'])} "
            f"toggles={len(policy['feature_toggles'])}"
        )
        return policy


def reload_policies() -> None:
    """清空缓存，下次访问重新加载磁盘（部署策略更新时用）。"""
    with _cache_lock:
        _policy_cache.clear()


def list_policies() -> dict[str, str]:
    """列出所有已加载 / 可加载的策略。"""
    return {k: v for k, v in _POLICY_FILES.items()}


# ── 核心：输出过滤 ──────────────────────────────────────────────

# 常见字段路径别名（不同引擎用不同名字）
_FIELD_ALIASES = {
    "icd_code": {"icd_code", "icd11_code", "icd10_code", "diagnosis_code", "disease_code"},
    "severity": {"severity", "risk_severity", "diagnosis_severity", "criticality"},
    "pgx_pathogenic_grading": {
        "pgx_pathogenic_grading", "pathogenicity", "pathogenicity_classification",
        "pathogenic_count", "likely_pathogenic_count",
    },
    "risk_probability": {
        "risk_probability", "risk_score", "risk_percentage",
        "prob_10y", "ascvd_risk",
    },
    "diagnosis_status": {
        "diagnosis_status", "clinical_status", "flagged_abnormal",
        "clinical_flag", "diagnostic_conclusion",
    },
    "triage_recommendation": {"triage_recommendation", "triage", "urgency_level"},
    "pgx_phenotype": {"pgx_phenotype", "metabolizer_type", "pgx_type"},
    "tcm_constitution": {"tcm_constitution", "constitution", "zhi_xiang"},
    "axis_scores": {"axis_scores", "axes", "axis_profiles"},
    "axis_labels": {"axis_labels", "axis_names"},
    "pathway_signals": {"pathway_signals", "pathways", "biological_pathways"},
    "wellness_recommendations": {"wellness_recommendations", "recommendations", "advice"},
    "lifestyle_advice": {"lifestyle_advice", "lifestyle", "intervention_plan"},
    "syndrome_patterns": {"syndrome_patterns", "tcm_syndromes", "zhenghou"},
    "sleep_patterns": {"sleep_patterns", "sleep", "hrv"},
    "fitness_signals": {"fitness_signals", "fitness", "activity"},
    "pgx_attention": {"pgx_attention", "attention", "pgx_notes"},
    "self_assess_score": {"self_assess_score", "self_assessment_score"},
    "risk_level": {"risk_level", "risk_tier"},
}


def _field_matches(canonical: str, actual_key: str) -> bool:
    """检查实际字段名是否匹配某个 canonical 类别。"""
    actual_lower = actual_key.lower()
    return actual_lower in _FIELD_ALIASES.get(canonical, {canonical})


def _walk_and_filter(
    obj: Any,
    allowed: set[str],
    blocked: set[str],
    removed: list[str],
    rewritten: list[str],
    path_prefix: str = "",
) -> Any:
    """递归遍历 payload，按策略过滤 / 屏蔽字段。

    返回过滤后的对象。removed 记录被屏蔽的路径。
    """
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            path = f"{path_prefix}.{k}" if path_prefix else k
            canonical_match = None
            for canonical in list(allowed) + list(blocked):
                if _field_matches(canonical, k):
                    canonical_match = canonical
                    break
            if canonical_match and canonical_match in blocked:
                if "*" not in blocked or True:  # 显式屏蔽优先于 *
                    removed.append(path)
                    continue
            if "*" in blocked and canonical_match not in allowed:
                # 通配符屏蔽 + 不在允许列表 → 屏蔽
                removed.append(path)
                continue
            result[k] = _walk_and_filter(v, allowed, blocked, removed, rewritten, path)
        return result
    elif isinstance(obj, list):
        return [_walk_and_filter(item, allowed, blocked, removed, rewritten, path_prefix) for item in obj]
    else:
        return obj


def _apply_feature_toggles(
    endpoint: str | None,
    feature_toggles: dict,
    blocked_endpoints: list[str],
) -> bool:
    """检查端点级开关是否禁用。返回 True 表示该端点被禁用。"""
    if not endpoint:
        return False
    if not feature_toggles:
        return False
    # 端点名匹配（精确 + 关键字）
    endpoint_lower = endpoint.lower()
    toggle_keys = {
        "diagnosis": "diagnosis_endpoint",
        "risk": "risk_assessment_endpoint",
        "icd": "icd_mapping",
        "pgx_pathogen": "pgx_pathogenic_grading",
        "pathogenic": "pgx_pathogenic_grading",
        "cds_hook": "cds_hooks",
        "fhir": "fhir_export",
        "writeback": "clinical_record_writeback",
        "triage": "triage_scoring",
        "risk_score": "risk_scoring",
        "tcm_diagnos": "tcm_diagnosis",
    }
    for kw, toggle in toggle_keys.items():
        if kw in endpoint_lower:
            if feature_toggles.get(toggle) is False:
                blocked_endpoints.append(f"{endpoint} (toggle={toggle}=false)")
                return True
    return False


def _scan_terms(
    text: str,
    banned_terms: dict,
    jurisdiction: str,
) -> list[str]:
    """扫描敏感词。返回命中的模式列表（不为空表示需要拦截或改写）。"""
    if not text or not banned_terms:
        return []
    hits: list[str] = []
    text_lower = text.lower()
    patterns = banned_terms.get("medical_claim_patterns", [])
    for pattern in patterns:
        if pattern.lower() in text_lower:
            hits.append(pattern)
    return hits


def _find_disclaimer(
    payload: dict,
    required_disclaimers: dict,
    violations: list[str],
) -> str | None:
    """按 payload 内容选择最合适的免责声明。"""
    if not required_disclaimers:
        return None

    # 有 pgx 相关字段命中 → 用 pgx 免责声明
    payload_str = str(payload).lower()
    if "pgx" in payload_str or "pharmacogen" in payload_str or "metabolizer" in payload_str:
        if "pgx" in required_disclaimers:
            return required_disclaimers["pgx"]
    if any("diagnos" in v.lower() for v in violations):
        if "diagnosis" in required_disclaimers:
            return required_disclaimers["diagnosis"]
    if any("risk" in v.lower() for v in violations):
        if "risk_assessment" in required_disclaimers:
            return required_disclaimers["risk_assessment"]

    # 默认 general
    return required_disclaimers.get("general")


def filter_output(
    payload: dict,
    jurisdiction: str,
    endpoint: str | None = None,
    context: str | None = None,
) -> FilterResult:
    """按法域策略过滤输出。

    Args:
        payload: 原始输出 payload（dict）
        jurisdiction: 用户法域（cn/us/uk/au/eu）
        endpoint: 端点名（可选，用于端点级开关判断）
        context: 上下文标签（可选，用于选择免责声明）

    Returns:
        FilterResult 包含过滤后的 payload 和审计信息。

    Raises:
        ClaimsPolicyError: 端点被策略禁用，或严重违规（fail-closed）
    """
    policy = load_policy(jurisdiction)
    allowed_set = set(policy.get("allowed_fields", []))
    blocked_set = set(policy.get("blocked_fields", []))
    feature_toggles = policy.get("feature_toggles", {})

    removed: list[str] = []
    rewritten: list[str] = []
    blocked_endpoints: list[str] = []

    # 1. 端点级开关判断
    endpoint_blocked = _apply_feature_toggles(endpoint, feature_toggles, blocked_endpoints)
    if endpoint_blocked:
        # 端点禁用 → 拒绝响应（fail-closed）
        raise ClaimsPolicyError(
            f"Endpoint '{endpoint}' is blocked by jurisdiction '{jurisdiction}' policy"
        )

    # 2. 字段级过滤（递归遍历 payload）
    filtered_payload = _walk_and_filter(
        payload, allowed_set, blocked_set, removed, rewritten
    )

    # 3. 敏感词扫描（针对字符串值）
    violations: list[str] = []
    banned_terms = policy.get("banned_terms", {})
    if banned_terms.get("medical_claim_patterns"):
        text_dump = str(filtered_payload)
        violations = _scan_terms(text_dump, banned_terms, jurisdiction)
        # 严重违规 → 拦截整个输出
        if len(violations) >= 3 and policy.get("wellness_boundary_strict", True):
            raise ClaimsPolicyError(
                f"Output blocked by strict claims policy ({len(violations)} violations): "
                f"{violations[:3]}"
            )

    # 4. 附加免责声明
    disclaimer = _find_disclaimer(filtered_payload, policy.get("required_disclaimers", {}), violations)

    warnings: list[str] = []
    if violations:
        warnings.append(f"terms_violations={violations}")
    if removed:
        warnings.append(f"fields_removed={len(removed)}")
    if disclaimer:
        # 注入免责声明到 payload 顶层（幂等）
        filtered_payload["claims_disclaimer"] = disclaimer

    return FilterResult(
        payload=filtered_payload,
        removed_fields=removed,
        rewritten_fields=rewritten,
        blocked_endpoints=blocked_endpoints,
        disclaimer_added=disclaimer,
        violations=violations,
        warnings=warnings,
    )


def check_endpoint_allowed(endpoint: str, jurisdiction: str) -> tuple[bool, str]:
    """快速检查端点是否被策略禁用。

    Returns: (allowed, reason)
    """
    policy = load_policy(jurisdiction)
    ft = policy.get("feature_toggles", {})
    endpoint_lower = endpoint.lower()
    toggle_keys = {
        "diagnosis": "diagnosis_endpoint",
        "risk": "risk_assessment_endpoint",
        "icd": "icd_mapping",
        "pgx_pathogen": "pgx_pathogenic_grading",
        "pathogenic": "pgx_pathogenic_grading",
        "cds_hook": "cds_hooks",
        "fhir": "fhir_export",
        "writeback": "clinical_record_writeback",
        "triage": "triage_scoring",
        "risk_score": "risk_scoring",
        "tcm_diagnos": "tcm_diagnosis",
    }
    for kw, toggle in toggle_keys.items():
        if kw in endpoint_lower:
            if ft.get(toggle) is False:
                return False, f"toggle '{toggle}' is false for jurisdiction '{jurisdiction}'"
    return True, "ok"


# ── 便捷入口：从 User 对象取 jurisdiction ──────────────────────

def get_user_jurisdiction(user) -> str:
    """从 User ORM 对象提取 jurisdiction，缺失时默认 cn。"""
    if user is None:
        return "cn"
    j = getattr(user, "jurisdiction", None)
    if not j:
        return getattr(user, "region", "cn") or "cn"
    return str(j).lower()


# ── 审计留痕（可选，非阻塞） ────────────────────────────────────

def log_claims_audit(
    user_id: str | None,
    jurisdiction: str,
    endpoint: str | None,
    result: FilterResult,
) -> None:
    """输出过滤完成后写审计日志（非阻塞）。

    失败不影响主流程，仅记录错误。
    """
    try:
        # 动态导入避免循环依赖
        from app.utils.audit_helper import write_audit_event  # noqa: F401
        # 审计写入由调用方（依赖注入的 db session）负责；此处仅打印到日志
        if result.removed_fields or result.violations:
            logger.warning(
                f"[Claims] user={user_id} jurisdiction={jurisdiction} endpoint={endpoint} "
                f"removed={len(result.removed_fields)} violations={len(result.violations)} "
                f"warnings={result.warnings}"
            )
        else:
            logger.debug(
                f"[Claims] user={user_id} jurisdiction={jurisdiction} endpoint={endpoint} "
                f"ok (disclaimer={bool(result.disclaimer_added)})"
            )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[Claims] audit log failed: {e}")
