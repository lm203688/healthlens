"""
healthlens_agent — HealthLens 智能体能力库（GOAI 榜单借鉴落地）

包含（无重型第三方依赖，融合引擎经 importlib 按需加载）：
  - safety   : 安全闸门（前置红牌 + 后置去医疗化/红线/证据断链）
  - audit    : 运行时行为遥测（七类异常）
  - pipeline : 融合安全管线（两道闸门 + 审计 接入真实融合引擎）
  - team     : 四角色 Agent 团队（Planner/Executor/Critic/Referee）
  - benchmark: GOAI 七维度行为评测 + launch-risk score
  - flow     : 可复现融合 DAG pipeline
  - multimodal: 多模态八轴倾向速判原型

运行：
  python -m healthlens_agent [pipeline|team|bench|flow|probe|safety|audit|all]
"""

from __future__ import annotations

from .audit import AuditEvent, AuditorConfig, RuntimeAuditor, ToolCall
from .benchmark import PROBES, DimResult, Probe, evaluate
from .flow import DEFAULT_DAG, DEFAULT_OPS, Operator, Storage, run_flow
from .multimodal import (
    MultimodalReport,
    VisualToolResult,
    analyze,
    tool_body_posture,
    tool_face_color,
    tool_tongue_coat,
    tool_tongue_color,
)
from .pipeline import PipelineResult, UserProfile, disclaimer, recommend, run_pipeline
from .safety import (
    RULES,
    Finding,
    GateResult,
    GuardCategory,
    GuardRule,
    Severity,
    build_rules,
    post_gate,
    pre_gate,
)
from .team import CriticReview, Plan, critic, executor, planner, referee, team_run

__version__ = "0.1.0"

__all__ = [
    "GuardCategory",
    "Severity",
    "Finding",
    "GateResult",
    "GuardRule",
    "pre_gate",
    "post_gate",
    "build_rules",
    "RULES",
    "ToolCall",
    "AuditEvent",
    "AuditorConfig",
    "RuntimeAuditor",
    "PipelineResult",
    "run_pipeline",
    "UserProfile",
    "recommend",
    "disclaimer",
    "Plan",
    "CriticReview",
    "planner",
    "executor",
    "critic",
    "referee",
    "team_run",
    "Probe",
    "DimResult",
    "PROBES",
    "evaluate",
    "Storage",
    "Operator",
    "run_flow",
    "DEFAULT_DAG",
    "DEFAULT_OPS",
    "VisualToolResult",
    "MultimodalReport",
    "analyze",
    "tool_tongue_color",
    "tool_tongue_coat",
    "tool_face_color",
    "tool_body_posture",
]
