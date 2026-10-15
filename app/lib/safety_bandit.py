"""安全约束 LinearUCB —— L1-3（2026-10-15）

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L1-3

三个组件：
    1. SafetyMask：把 tcm_safety / claims_engine / critical_values 三块护栏
       拼成一个"动作-用户上下文" → {allowed, reasons} 的决策门。任何一条命中
       硬约束（十八反、妊娠禁用、危急值）即屏蔽。
    2. LinUCB：纯 Python 的 LinearUCB 实现（无 numpy 依赖，用 list[list] + 手工
       高斯消元求逆），接口 A_inv / b / predict / update。
    3. SafetyBanditPolicy：先过 SafetyMask，被屏蔽的动作在 predict 时强制
       返回 -inf，从 argmax 中排除；输出 {action, reward_expected, mask_log}。

wellness 边界：全部标注 not_clinical=True，仅描述"若坚持某些干预，健康信号
可能如何演化"的参考推演，不构成任何诊断、治疗或个体结果预测。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from app.core.tcm_safety import check_safety as _tcm_check
from app.lib.critical_values import check_critical_values as _cv_check
from app.lib.claims_engine import check_endpoint_allowed as _ce_check


# ---------------------------------------------------------------------------
# 1. SafetyMask
# ---------------------------------------------------------------------------


@dataclass
class SafetyDecision:
    """SafetyMask 一次判定。"""
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "findings": list(self.findings),
        }


class SafetyMask:
    """包装 tcm_safety + claims_engine + critical_values 为统一"动作门"。

    输入：candidate_action = {"intervention": "xxx", "dose": yyy, "herbs": [...], ...}
          user_context = {"pregnancy": bool, "medications": [...], "foods": [...],
                          "biomarkers": {...}, "jurisdiction": "cn"}
    输出：SafetyDecision{allowed, reasons, findings}

    判定逻辑（顺序 fail-closed，只要有一条硬命中即屏蔽）：
        1) 十八反/十九畏/妊娠禁忌/中西药相互作用 → tcm_safety
        2) 危急值 → critical_values
        3) 端点策略 → claims_engine.check_endpoint_allowed
    """

    def __init__(self, strict: bool = True):
        # strict=True 表示：任一高危告警即屏蔽（默认）
        self.strict = strict

    def check(
        self,
        candidate_action: dict[str, Any],
        user_context: dict[str, Any],
    ) -> SafetyDecision:
        reasons: list[str] = []
        findings: list[dict] = []

        # 1) TCM 安全
        herbs = list(candidate_action.get("herbs") or [])
        formulas = list(candidate_action.get("formulas") or [])
        meds_from_ctx = list(user_context.get("medications") or [])
        foods_from_ctx = list(user_context.get("foods") or [])
        herbs.extend(list(candidate_action.get("medications") or []))
        meds_from_ctx.extend(list(user_context.get("medications") or []))

        tcm_report = _tcm_check(
            herbs=herbs,
            formulas=formulas,
            medications=meds_from_ctx,
            foods=foods_from_ctx,
            pregnancy=bool(user_context.get("pregnancy", False)),
        )
        for f in tcm_report.findings:
            findings.append({
                "kind": f"tcm::{f.kind}",
                "severity": f.severity,
                "detail": f.detail,
                "advice": f.advice,
            })
            if f.severity == "high" or (self.strict and f.severity == "moderate"):
                reasons.append(f"[tcm] {f.detail}")

        # 2) 危急值：动作里带生物标志物 / 用户上下文里带生物标志物
        biomarkers = {
            **(user_context.get("biomarkers") or {}),
            **(candidate_action.get("biomarkers") or {}),
        }
        cv_hits = _cv_check(biomarkers) if biomarkers else []
        for hit in cv_hits:
            d = hit.as_dict()
            findings.append({
                "kind": "critical_value",
                "severity": "high",
                "detail": f"危急值：{d['label']}={d['value']}（阈值 {d['threshold']}）",
                "advice": "建议立即就医评估",
            })
            reasons.append(f"[critical_value] {d['label']}={d['value']} 触发危急值")

        # 3) 端点策略：把 candidate_action 里的 endpoint 字段映射到 claims_engine
        endpoint = candidate_action.get("endpoint")
        jurisdiction = user_context.get("jurisdiction", "cn")
        if endpoint:
            allowed, why = _ce_check(endpoint, jurisdiction)
            if not allowed:
                reasons.append(f"[claims] endpoint {endpoint} 被法域 {jurisdiction} 禁用：{why}")
                findings.append({
                    "kind": "claims_policy",
                    "severity": "high",
                    "detail": f"{endpoint} 被法域策略屏蔽：{why}",
                    "advice": "切换法域或关闭该端点",
                })

        # 4) 未知干预名 → 直接屏蔽（fail-loud）
        intervention = candidate_action.get("intervention")
        if not intervention:
            reasons.append("[policy] 候选动作缺少 intervention 字段")

        return SafetyDecision(allowed=(not reasons), reasons=reasons, findings=findings)

    def batch_check(
        self,
        actions: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> list[SafetyDecision]:
        return [self.check(a, user_context) for a in actions]


# ---------------------------------------------------------------------------
# 2. 纯 Python 线性代数（d × d）
# ---------------------------------------------------------------------------


def _eye(d: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]


def _mat_vec(mat: list[list[float]], v: list[float]) -> list[float]:
    return [sum(m[j] * v[j] for j in range(len(mat[0]))) for m in mat]


def _mat_add(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    n = len(a)
    m = len(a[0])
    return [[a[i][j] + b[i][j] for j in range(m)] for i in range(n)]


def _outer(u: list[float], v: list[float]) -> list[list[float]]:
    return [[u[i] * v[j] for j in range(len(v))] for i in range(len(u))]


def _inv(mat: list[list[float]]) -> list[list[float]]:
    """高斯-约当求逆。要求方阵。"""
    n = len(mat)
    # 增广矩阵 [A | I]
    aug = [[mat[i][j] for j in range(n)] + [1.0 if i == j else 0.0 for j in range(n)]
           for i in range(n)]
    for col in range(n):
        # 部分主元
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) < 1e-12:
            raise ValueError("矩阵奇异，无法求逆")
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pv = aug[col][col]
        aug[col] = [x / pv for x in aug[col]]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            aug[r] = [aug[r][c] - factor * aug[col][c] for c in range(2 * n)]
    return [row[n:] for row in aug]


def _mat_inv_mul(mat_inv: list[list[float]], vec: list[float]) -> list[float]:
    """mat_inv * vec。"""
    return _mat_vec(mat_inv, vec)


# ---------------------------------------------------------------------------
# 3. LinUCB
# ---------------------------------------------------------------------------


class LinUCB:
    """纯 Python LinearUCB 实现（无 numpy 依赖）。

    Args:
        d: 特征维度
        alpha: 探索系数（>0；越大越探索）
        ridge: 岭正则化系数 λ（初值 I + λI 的稳定化因子，通常 1.0）
    """

    def __init__(self, d: int, alpha: float = 1.0, ridge: float = 1.0):
        if d <= 0:
            raise ValueError(f"d 必须 > 0，收到 {d}")
        if alpha < 0:
            raise ValueError("alpha 必须 >= 0")
        self.d = d
        self.alpha = float(alpha)
        self.ridge = float(ridge)
        self.A = _eye(d)
        for i in range(d):
            self.A[i][i] += self.ridge
        self.b = [0.0] * d
        self.A_inv = _inv(self.A)
        self.n_updates = 0

    def predict(self, features: list[float]) -> float:
        """返回 Q 值（点估计 + UCB 上界）。被 SafetyBanditPolicy 用于选择。

        公式：Q(x) = θᵀx + α·sqrt(xᵀ A⁻¹ x)
        θ = A⁻¹ b
        """
        self._check_feature_len(features)
        theta = _mat_inv_mul(self.A_inv, self.b)
        # xᵀ A⁻¹ x：先算 A⁻¹ x（向量），再点乘 x
        ainv_x = _mat_vec(self.A_inv, features)
        x_at = sum(f * v for f, v in zip(features, ainv_x))
        ucb = self.alpha * math.sqrt(max(0.0, x_at))
        q_hat = sum(t * f for t, f in zip(theta, features))
        return q_hat + ucb

    def predict_all(self, feature_lists: list[list[float]]) -> list[float]:
        return [self.predict(f) for f in feature_lists]

    def update(self, features: list[float], reward: float) -> None:
        """贝叶斯更新：A ← A + xxᵀ，b ← b + r·x，然后重求逆。"""
        self._check_feature_len(features)
        self.A = _mat_add(self.A, _outer(features, features))
        self.b = [self.b[i] + reward * features[i] for i in range(self.d)]
        try:
            self.A_inv = _inv(self.A)
        except ValueError:
            # 数值奇异：退化为对角 1e-6（保持算法可继续，避免崩溃）
            for i in range(self.d):
                self.A[i][i] += 1e-6
            self.A_inv = _inv(self.A)
        self.n_updates += 1

    def _check_feature_len(self, features: list[float]) -> None:
        if len(features) != self.d:
            raise ValueError(
                f"特征长度 {len(features)} 与 LinUCB 维度 {self.d} 不一致"
            )

    def state(self) -> dict:
        return {
            "d": self.d,
            "alpha": self.alpha,
            "n_updates": self.n_updates,
        }


# ---------------------------------------------------------------------------
# 4. SafetyBanditPolicy
# ---------------------------------------------------------------------------


@dataclass
class BanditStepResult:
    """一次 policy.step 的返回。"""
    action: dict[str, Any] | None
    reward_expected: float
    q_values: dict[str, float]
    mask_log: list[SafetyDecision]
    chosen_index: int | None
    not_clinical: bool = True
    disclaimer: str = (
        "bandit 决策为健康信号层面的干预选择参考，不构成任何诊断、治疗或个体结果预测。"
    )

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "reward_expected": round(self.reward_expected, 4)
            if not math.isinf(self.reward_expected) else self.reward_expected,
            "q_values": {k: round(v, 4) if not math.isinf(v) else v
                         for k, v in self.q_values.items()},
            "mask_log": [m.as_dict() for m in self.mask_log],
            "chosen_index": self.chosen_index,
            "not_clinical": self.not_clinical,
            "disclaimer": self.disclaimer,
        }


class SafetyBanditPolicy:
    """组装 SafetyMask + LinUCB：先过 mask，再 LinUCB argmax。

    Args:
        bandit: LinUCB 实例
        mask: SafetyMask 实例
        feature_builder: 从 (user_context, candidate_action) 产出 d 维特征向量
    """

    def __init__(
        self,
        bandit: LinUCB,
        mask: SafetyMask,
        feature_builder: Any | None = None,
    ):
        self.bandit = bandit
        self.mask = mask
        # 默认特征：把 intervention 名字哈希 + 剂量 + 上下文维度编码成 d 维
        self._feature_builder = feature_builder or _default_feature_builder

    def step(
        self,
        user_context: dict[str, Any],
        candidate_actions: list[dict[str, Any]],
        action_id_key: str = "intervention",
    ) -> BanditStepResult:
        """选动作。

        - 空候选 → 返回 None + fail-loud 标记
        - 全部被屏蔽 → 返回 None（mask_log 完整留痕）
        - 合法子集 → LinUCB.predict 打分，取 argmax

        被屏蔽的动作在 predict 时强制 -inf，从 argmax 排除。
        """
        if not candidate_actions:
            return BanditStepResult(
                action=None,
                reward_expected=math.inf,  # 无意义，保持类型
                q_values={},
                mask_log=[],
                chosen_index=None,
            )

        # 1) 全量过 mask
        mask_log = self.mask.batch_check(candidate_actions, user_context)

        # 2) 计算 Q 值（被屏蔽 → -inf）
        q_values: dict[str, float] = {}
        features: dict[str, list[float]] = {}
        for i, action in enumerate(candidate_actions):
            aid = str(action.get(action_id_key, f"action_{i}"))
            if not mask_log[i].allowed:
                q_values[aid] = -math.inf
                features[aid] = self._feature_builder(user_context, action)
                continue
            feat = self._feature_builder(user_context, action)
            features[aid] = feat
            q_values[aid] = self.bandit.predict(feat)

        # 3) 选合法子集内 argmax
        legal = [(i, a) for i, a in enumerate(candidate_actions) if mask_log[i].allowed]
        if not legal:
            return BanditStepResult(
                action=None,
                reward_expected=-math.inf,
                q_values=q_values,
                mask_log=mask_log,
                chosen_index=None,
            )

        best_i, best_action = max(
            legal,
            key=lambda pa: q_values[str(pa[1].get(action_id_key, f"action_{pa[0]}"))],
        )
        best_q = q_values[str(best_action.get(action_id_key, f"action_{best_i}"))]

        return BanditStepResult(
            action=best_action,
            reward_expected=best_q,
            q_values=q_values,
            mask_log=mask_log,
            chosen_index=best_i,
        )

    def update(self, action: dict[str, Any], reward: float) -> None:
        """根据 (feature, reward) 更新 bandit（不重复过 mask；由调用方保证合法）。"""
        user_context = {}
        feat = self._feature_builder(user_context, action)
        self.bandit.update(feat, reward)

    def status(self) -> dict:
        return {
            "bandit": self.bandit.state(),
            "n_actions_seen": self.bandit.n_updates,
            "not_clinical": True,
        }


def _default_feature_builder(
    user_context: dict[str, Any], candidate_action: dict[str, Any],
) -> list[float]:
    """默认特征：把 intervention 名字、剂量、用户维度编码为定长 5 维向量。

    维度：
        0: intervention_name_hash / 256
        1: dose / 100
        2: pregnancy (0/1)
        3: n_medications / 10
        4: jurisdiction_cn (1 if cn else 0)
    """
    name = str(candidate_action.get("intervention", ""))
    dose = float(candidate_action.get("dose", 0.0))
    name_hash = sum(ord(c) for c in name) % 256
    n_meds = len(user_context.get("medications") or [])
    jur = user_context.get("jurisdiction", "cn")
    return [
        name_hash / 256.0,
        dose / 100.0,
        1.0 if user_context.get("pregnancy") else 0.0,
        n_meds / 10.0,
        1.0 if jur == "cn" else 0.0,
    ]


# 便于外部构造 policy 时的默认工厂
def build_policy(
    alpha: float = 1.0,
    d: int = 5,
    strict: bool = True,
    feature_builder: Any | None = None,
) -> SafetyBanditPolicy:
    return SafetyBanditPolicy(
        bandit=LinUCB(d=d, alpha=alpha),
        mask=SafetyMask(strict=strict),
        feature_builder=feature_builder,
    )


if __name__ == "__main__":  # pragma: no cover
    import json
    policy = build_policy(alpha=1.5, d=5)
    ctx = {"pregnancy": False, "medications": [], "jurisdiction": "cn",
           "biomarkers": {"potassium": 4.5}}
    actions = [
        {"intervention": "anti_inflammatory_diet", "dose": 1.0},
        {"intervention": "supplement_A", "dose": 0.5, "herbs": ["甘草", "海藻"]},
        {"intervention": "exercise_aerobic", "dose": 1.0},
    ]
    r = policy.step(ctx, actions)
    print(json.dumps(r.as_dict(), ensure_ascii=False, indent=2))
