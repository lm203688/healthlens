"""Unified pipeline registry: agent-lib + health-agent + data-flow."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_pipeline():
    """返回 (UserProfile, run_pipeline) 供其他模块调用。"""
    from healthlens_agent.pipeline import UserProfile, run_pipeline

    return UserProfile, run_pipeline


ALL_PHASES = [
    ("risk_engine", "risk_engine", "Risk engine (8-axis scoring)"),
    ("safety_layer", "safety_layer", "Safety gate + escalation"),
    ("audit_trail", "audit_trail", "Runtime audit logging"),
    ("fusion_engine", "fusion_engine", "Fusion + recommendation"),
    ("feedback_loop", "feedback_loop", "User feedback loop"),
    ("ops_monitor", "ops_monitor", "Ops monitoring + alerts"),
    ("collect", "data_collect", "情报采集 (phase 1)"),
    ("analyze", "data_analyze", "分析 (phase 2)"),
    ("decide", "data_decide", "决策 (phase 3)"),
    ("develop", "data_develop", "开发 (phase 4)"),
    ("test", "data_test", "测试 (phase 5)"),
    ("deploy", "data_deploy", "部署 (phase 6)"),
    ("feedback", "data_feedback", "反馈 (phase 7)"),
    ("ops", "data_ops", "运维 (phase 8)"),
]

LIB_PHASES = {"risk_engine", "safety_layer", "audit_trail", "fusion_engine", "feedback_loop", "ops_monitor"}
DATA_PHASES = {"collect", "analyze", "decide", "develop", "test", "deploy", "feedback", "ops"}

# 数据流阶段名 → auto_pipeline 整数 ID 映射（与 auto-pipeline/scripts 目录语义一致）
DATA_PHASE_ID_MAP = {
    "collect": 1,
    "analyze": 2,
    "decide": 3,
    "develop": 4,
    "test": 5,
    "deploy": 6,
    "feedback": 7,
    "ops": 8,
}

# 旧命名别名（deprecated）：曾用数据管线语义命名，与实际目录语义不符，保留仅为兼容旧调用
DEPRECATED_ALIASES = {
    "clean": "analyze",
    "sync": "decide",
    "risk_analysis": "develop",
    "constitution": "test",
    "fusion_analysis": "deploy",
}


def resolve_phase_id(phase_id: str) -> tuple[str, str | None]:
    """解析阶段 ID，返回 (规范ID, 弃用警告)。

    若传入旧别名，返回对应的新 ID 与一条警告，避免静默执行到语义不符的阶段。
    """
    if phase_id in DEPRECATED_ALIASES:
        new_id = DEPRECATED_ALIASES[phase_id]
        return new_id, (
            f"阶段 ID '{phase_id}' 已弃用，其实际执行的是 "
            f"'{new_id}' (phase {DATA_PHASE_ID_MAP[new_id]})；请改用 '{new_id}'。"
        )
    return phase_id, None


def list_all_phases() -> list[dict]:
    """列出所有管线阶段。"""
    return [{"id": pid, "type": typ, "name": name} for pid, typ, name in ALL_PHASES]


# ──────────────────────────────────────────────
# Real handler factory
# ──────────────────────────────────────────────


def _risk_handler(inputs: dict | None) -> dict:
    """风险引擎：8 轴风险评分。"""
    from healthlens_agent.pipeline import UserProfile, run_pipeline

    inputs = inputs or {}
    user_input = inputs.get("user_input", "")
    profile = UserProfile(
        pathway_scores=inputs.get("pathway_scores") or {},
        weak_axes=set(inputs.get("weak_axes", [])),
        contraindications=set(inputs.get("contraindications", [])),
    )
    result = run_pipeline(user_input or "general_assessment", profile)
    r = result.to_dict()
    scores = r.get("axis_scores", r.get("risk_scores", {}))
    red_flags = r.get("red_flags", r.get("alerts", []))
    return {
        "status": "ok",
        "phase": "risk_engine",
        "axis_scores": scores,
        "red_flags": red_flags,
        "has_risk": bool(red_flags),
    }


def _safety_handler(inputs: dict | None) -> dict:
    """安全层：前置拦截 + 分级处理。"""
    from healthlens_agent.pipeline import UserProfile, run_pipeline

    inputs = inputs or {}
    user_input = inputs.get("user_input", "")
    profile = UserProfile(
        pathway_scores=inputs.get("pathway_scores") or {},
        weak_axes=set(inputs.get("weak_axes", [])),
        contraindications=set(inputs.get("contraindications", [])),
    )
    result = run_pipeline(user_input or "safety_check", profile)
    r = result.to_dict()
    red_flags = r.get("red_flags", r.get("alerts", []))
    gated = r.get("gated", False)
    return {
        "status": "ok",
        "phase": "safety_layer",
        "gated": gated,
        "red_flags": red_flags,
        "escalation_needed": bool(red_flags),
        "disclaimer": r.get("disclaimer", ""),
    }


def _audit_handler(inputs: dict | None) -> dict:
    """审计日志：记录运行时操作。"""
    from healthlens_agent.audit import RuntimeAuditor, ToolCall

    inputs = inputs or {}
    auditor = RuntimeAuditor()
    call = ToolCall(agent="pipeline_registry", tool="phase_call", args=str(inputs), result="ok")
    events = auditor.audit([call])
    return {
        "status": "ok",
        "phase": "audit_trail",
        "event_count": len(events),
        "events": [str(e) for e in events],
        "auditor_config": str(auditor.cfg),
    }


def _fusion_handler(inputs: dict | None) -> dict:
    """融合引擎：个性化推荐。"""
    from healthlens_agent.pipeline import UserProfile, recommend

    inputs = inputs or {}
    profile = UserProfile(
        pathway_scores=inputs.get("pathway_scores") or {},
        weak_axes=set(inputs.get("weak_axes", [])),
        contraindications=set(inputs.get("contraindications", [])),
    )
    cases = inputs.get("cases")
    result = recommend(profile, cases=cases, top_k=inputs.get("top_k", 8))
    return {
        "status": "ok",
        "phase": "fusion_engine",
        "recommendations": result.get("recommendations", []),
        "weak_pathways": result.get("weak_pathways", []),
        "weak_axes": result.get("weak_axes", []),
        "llm_enabled": result.get("llm_enabled", False),
    }


def _feedback_handler(inputs: dict | None) -> dict:
    """反馈闭环。"""
    from healthlens_agent.feedback_loop import run_feedback_analysis
    return run_feedback_analysis(inputs)


def _ops_handler(inputs: dict | None) -> dict:
    """运行监控。"""
    from healthlens_agent.ops_monitor import run_ops_check
    return run_ops_check(inputs)


LIB_HANDLERS = {
    "risk_engine": _risk_handler,
    "safety_layer": _safety_handler,
    "audit_trail": _audit_handler,
    "fusion_engine": _fusion_handler,
    "feedback_loop": _feedback_handler,
    "ops_monitor": _ops_handler,
}


def get_handler(phase_id: str):
    """获取阶段 handler：agent-lib 阶段返回真实实现，data-flow 阶段返回 auto_pipeline 包装器。"""
    if phase_id in LIB_HANDLERS:
        return LIB_HANDLERS[phase_id]

    if phase_id in DATA_PHASES:
        from healthlens_agent.auto_pipeline import run_phase as _run_phase

        phase_num = DATA_PHASE_ID_MAP[phase_id]

        def wrapper(inputs: dict | None = None) -> dict:
            inputs = inputs or {}
            result = _run_phase(phase_num, dry_run=False, **inputs)
            if isinstance(result, dict):
                result.setdefault("phase", phase_id)
                result["phase_number"] = phase_num
            return result

        return wrapper

    # 旧别名：解析到规范 ID 并注入弃用警告，避免静默执行到语义不符的阶段
    canonical, warning = resolve_phase_id(phase_id)
    if canonical in DATA_PHASES:
        from healthlens_agent.auto_pipeline import run_phase as _run_phase

        phase_num = DATA_PHASE_ID_MAP[canonical]

        def legacy_wrapper(inputs: dict | None = None) -> dict:
            inputs = inputs or {}
            result = _run_phase(phase_num, dry_run=False, **inputs)
            if isinstance(result, dict):
                result.setdefault("phase", canonical)
                result["requested_phase"] = phase_id
                result["phase_number"] = phase_num
                result["deprecation_warning"] = warning
            return result

        return legacy_wrapper

    # 未知阶段返回 stub
    def _stub(inputs: dict | None = None) -> dict:
        hint = ""
        if canonical != phase_id:
            hint = f" {warning}"
        return {
            "status": "not_implemented",
            "phase": phase_id,
            "message": f"Phase '{phase_id}' not found in registry.{hint}",
        }

    return _stub
