"""充分统计量协议（Sufficient Statistics Protocol）— HealthLens L3 联邦证据网络

出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L3「联邦证据网络」
      ——「不要承诺做不到的事。小样本 + DP 会让效应估计崩塌。正确表述是
      『个体数据不出域 + 只共享充分统计量』，而非『DP 保障的联邦学习』。」

**核心命题**：租户（医疗机构/合作方）本地聚合完 n-of-1 效应估计后，
只上传 `SufficientStats` 到中心；中心端**从协议层拒绝**接收 raw samples。
本文件是"个体数据不出域"承诺的代码级闸门。

**明确禁止**：
- 函数签名里不出现 `list[float]` / `np.ndarray` 等样本承载体。
- `validate_tenant_payload` 对任意 `list`/`np.ndarray` 字段一律记录违规。
- 唯一哈希（`hash_stats`）用 sha256 对**规范化 JSON** 计算，供外部审计比对。

设计约束：
- 仅依赖标准库；不引入 numpy/pandas。
- 无 side effect：所有函数纯函数化，便于单测与签名冻结。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SufficientStats:
    """单个租户上传的**充分统计量**（不含任何个体样本）。

    Fields:
        tenant_id: 租户唯一标识。
        n: 该租户纳入分析的 n-of-1 队列人数（正整数）。
        mean: 该租户 outcome 均值。
        var: 该租户 outcome 方差（无偏估计，非负）。
        effect_estimate: 局部处理效应点估计（如 log-odds、Cohen's d、SMD）。
        effect_se: 局部处理效应标准误（正数）。
        covariate_summary: 分层维度（region/age-band/gender/axis 等）的聚合统计。
            每个 value 必须是标量或标量列表（长度固定且不含个体级信息）。
    """

    tenant_id: str
    n: int
    mean: float
    var: float
    effect_estimate: float
    effect_se: float
    covariate_summary: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """规范化 JSON 序列化（供 hash_stats 与 API 传输共用）。"""
        return json.dumps(
            {
                "tenant_id": self.tenant_id,
                "n": self.n,
                "mean": self.mean,
                "var": self.var,
                "effect_estimate": self.effect_estimate,
                "effect_se": self.effect_se,
                "covariate_summary": self.covariate_summary,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_tenant_payload(payload: Mapping[str, Any]) -> list[str]:
    """校验租户上传的充分统计量字典。

    返回违规清单（空 = 通过）；调用方决定是否 400。协议层硬性拒绝：
    1. 缺字段；
    2. 数值越界（n<=0 / var<0 / effect_se<=0）；
    3. 数值不是有限实数（NaN/Inf 拒绝，防 DP-adjacent 数值攻击）；
    4. covariate_summary 中出现 list-of-list / np.ndarray / set / 嵌套 dict，
       这些是 raw sample 的常见伪装形态。

    Args:
        payload: dict-like，键集合与 SufficientStats 字段一致。

    Returns:
        list of violation messages（空列表 = 通过）。
    """
    violations: list[str] = []

    required = {
        "tenant_id",
        "n",
        "mean",
        "var",
        "effect_estimate",
        "effect_se",
        "covariate_summary",
    }
    missing = required - set(payload.keys())
    if missing:
        violations.append(f"missing_fields: {sorted(missing)}")

    # tenant_id
    tid = payload.get("tenant_id")
    if not isinstance(tid, str) or not tid.strip():
        violations.append("tenant_id_must_be_nonempty_string")

    # n
    n = payload.get("n")
    if not isinstance(n, int) or isinstance(n, bool):
        violations.append("n_must_be_int")
    elif n <= 0:
        violations.append("n_must_be_positive")

    # mean / var / effect_estimate / effect_se
    for key in ("mean", "var", "effect_estimate", "effect_se"):
        v = payload.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            violations.append(f"{key}_must_be_finite_number")
            continue
        if not math.isfinite(v):
            violations.append(f"{key}_must_be_finite")

    var = payload.get("var")
    if isinstance(var, (int, float)) and not isinstance(var, bool) and math.isfinite(var) and var < 0:
        violations.append("var_must_be_nonnegative")

    effect_se = payload.get("effect_se")
    if isinstance(effect_se, (int, float)) and not isinstance(effect_se, bool) and math.isfinite(effect_se) and effect_se <= 0:
        violations.append("effect_se_must_be_positive")

    # covariate_summary：只接受 dict；禁 list-of-list / set / 深嵌套
    cov = payload.get("covariate_summary")
    if not isinstance(cov, dict):
        violations.append("covariate_summary_must_be_dict")
    else:
        for k, v in cov.items():
            if not isinstance(k, str):
                violations.append("covariate_summary_key_must_be_string")
                break
            if isinstance(v, (list, tuple)) and len(v) > 0 and any(
                isinstance(x, (list, tuple, dict, set)) for x in v
            ):
                violations.append(f"covariate_summary.{k}_contains_nested_sample")
                break
            if isinstance(v, (set, frozenset)):
                violations.append(f"covariate_summary.{k}_is_set_not_aggregate")
                break
            # 嵌套 dict 允许（分层聚合），但不允许任意深
            if isinstance(v, dict) and any(isinstance(x, list) and x for x in v.values()):
                violations.append(f"covariate_summary.{k}_nested_list")
                break

    # 硬拒绝 raw samples：任何键包含 sample/row/records/data 一律拒绝
    forbidden_keys = {"samples", "raw_samples", "rows", "records", "observations", "data"}
    hit = set(payload.keys()) & forbidden_keys
    if hit:
        violations.append(f"raw_sample_fields_rejected: {sorted(hit)}")

    # 任何值为 list/np.ndarray-like 且长度 > 3（个体样本典型形态）→ 拒绝
    for k, v in payload.items():
        if isinstance(v, list) and len(v) > 3 and all(isinstance(x, (int, float)) for x in v):
            violations.append(f"field_{k}_looks_like_raw_sample_list")

    return violations


# ---------------------------------------------------------------------------
# 内容寻址哈希（防篡改 / 便于审计）
# ---------------------------------------------------------------------------


def hash_stats(stats: SufficientStats) -> str:
    """对 SufficientStats 计算 sha256 内容寻址哈希。

    规范化：sort_keys=True + 无空白 separators，保证不同进程哈希一致。
    用途：
      1. API 层回传给租户证明"只上传了充分统计量"；
      2. 中心端存储时做防篡改校验；
      3. 外部审计比对（Zenodo DOI 场景）。
    """
    payload = stats.to_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
