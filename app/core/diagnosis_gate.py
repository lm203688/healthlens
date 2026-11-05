"""解释↔诊断边界层（Boundary Layer）— HealthLens 定位重构 P1
============================================================

**架构目的（一次做对，避免返工/越界）**：

HealthLens 是精准健康养生平台（非医疗）。为守住 wellness 边界，把
「**解释**」与「**诊断**」从架构层彻底分离：

  ┌─────────────────────────────────────────────────────────────┐
  │  解释层（Interpretation）— 默认启用、默认安全                 │
  │  · 八轴稳态 + 五层因果链的「状态解读」                         │
  │  · 风险分层（risk stratification）                            │
  │  · 偏离定位（deviation localization）                         │
  │  · 输出 = 健康评估 + 趋势预警，**不含疾病结论**                │
  └──────────────────────────┬──────────────────────────────────┘
                             │ 边界（Boundary）
  ┌──────────────────────────▼──────────────────────────────────┐
  │  诊断层（Diagnosis）— 独立门控模块                            │
  │  · 可插拔 / 单独验证 / 单独注册                                │
  │  · 默认 **inactive**（不激活，留接口）                         │
  │  · 激活 = 「要不要注册医疗器械」的分水岭决策点                  │
  │  · 激活前仅返回 not_active，不执行任何诊断逻辑                  │
  └─────────────────────────────────────────────────────────────┘

**设计要点**：
1. `DiagnosisGate` 是单例式门控，默认 `active=False`。
2. `interpret()` 永远可用（解释是平台核心能力，非医疗器械行为）。
3. `diagnose()` 在 gate 未激活时**不执行**任何诊断逻辑，直接返回
   `not_active` 结构化响应——fail-closed，绝不降级放行。
4. 激活开关由环境变量 `HEALTHLENS_DIAGNOSIS_GATE` 控制
   （"1"/"true"/"yes" 才激活；默认关闭）。生产环境必须显式决策。
5. 本模块只依赖标准库，可在精简环境（无 FastAPI）下独立导入/测试。

**诚实边界**：
- 本模块不声称「已验证诊断」；激活前它甚至不产生诊断输出。
- 诊断层如未来激活，仍属「研究性/探索性」工具，必须另行完成
  医疗器械分类评估与注册决策，不因本模块存在而自动获得任何资质。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateState(str, Enum):
    """门控状态。"""

    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class InterpretationResult:
    """解释层输出（健康评估，非诊断）。"""

    axis_scores: dict[str, Any] = field(default_factory=dict)
    risk_strata: str = "unknown"          # low / moderate / high / unknown
    deviations: list[str] = field(default_factory=list)   # 偏离定位
    trend_alerts: list[str] = field(default_factory=list) # 趋势预警
    summary: str = ""
    is_diagnosis: bool = False             # 恒定 False —— 这不是诊断
    disclaimer: str = (
        "本结果仅为健康状态解读与风险分层参考，不构成医疗诊断、"
        "处方或治疗建议。"
    )


@dataclass
class DiagnosisGateResponse:
    """诊断层响应（门控包装）。"""

    state: str = GateState.INACTIVE.value
    activated: bool = False
    result: Any = None
    reason: str = ""
    note: str = (
        "诊断模块当前未激活。HealthLens 仅提供 AI 辅助健康评估与风险分层，"
        "不提供独立诊断。任何诊断结论须由持牌医疗机构出具。"
    )


class DiagnosisGate:
    """解释↔诊断边界门控。

    默认 inactive。激活前 `diagnose()` 永不执行诊断逻辑（fail-closed）。
    """

    def __init__(self, active: bool | None = None) -> None:
        if active is None:
            active = self._from_env()
        self.active = bool(active)

    @staticmethod
    def _from_env() -> bool:
        raw = os.environ.get("HEALTHLENS_DIAGNOSIS_GATE", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    # ------------------------------------------------------------------
    # 解释层（Interpretation）—— 默认启用，安全，非诊断
    # ------------------------------------------------------------------
    def interpret(
        self,
        *,
        axis_scores: dict[str, Any] | None = None,
        risk_strata: str | None = None,
        deviations: list[str] | None = None,
        trend_alerts: list[str] | None = None,
        summary: str = "",
    ) -> InterpretationResult:
        """生成健康状态解读（解释层）。

        本方法**永不**输出疾病结论；仅汇总传入的八轴状态/风险分层/
        偏离定位/趋势预警为一次结构化的健康评估。
        """
        return InterpretationResult(
            axis_scores=axis_scores or {},
            risk_strata=risk_strata or "unknown",
            deviations=list(deviations or []),
            trend_alerts=list(trend_alerts or []),
            summary=summary,
            is_diagnosis=False,
        )

    # ------------------------------------------------------------------
    # 诊断层（Diagnosis）—— 独立门控，默认不激活
    # ------------------------------------------------------------------
    def diagnose(self, payload: Any = None) -> DiagnosisGateResponse:
        """执行诊断（仅在门控激活后）。

        gate 未激活 → 返回 not_active，**不执行任何诊断逻辑**。
        激活后仍应由诊断提供方（如持牌医疗机构）校验。
        """
        if not self.active:
            return DiagnosisGateResponse(
                state=GateState.INACTIVE.value,
                activated=False,
                result=None,
                reason="diagnosis_gate_inactive",
            )
        # 激活后的诊断逻辑由独立的诊断提供方实现（本框架仅占位）。
        return DiagnosisGateResponse(
            state=GateState.ACTIVE.value,
            activated=True,
            result={"status": "diagnosis_provider_not_registered"},
            reason="diagnosis_provider_not_registered",
            note=(
                "诊断模块已激活，但尚未注册独立诊断提供方。"
                "本框架不提供诊断结论。"
            ),
        )


# 模块级默认实例（可被测试覆盖，生产使用同一实例保证门控一致性）
_gate: DiagnosisGate | None = None


def get_gate() -> DiagnosisGate:
    """获取门控单例。"""
    global _gate
    if _gate is None:
        _gate = DiagnosisGate()
    return _gate
