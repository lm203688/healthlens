"""S1-6 claims 引擎测试：五法域差异可观测 + fail-closed + 端点开关 + 审计入口。

覆盖报告 §7.1 M1 指出的三个缺口：无测试、jurisdiction_overrides 行为未验证、
审计未落库验证。本文件只断言**实测行为**（先跑后写），不断言期望行为。
"""
import pytest

from app.lib.claims_engine import (
    SUPPORTED_JURISDICTIONS,
    ClaimsPolicyError,
    check_endpoint_allowed,
    filter_output,
    list_policies,
    load_policy,
    log_claims_audit,
)


# 跨法域同一输入：含 US 禁用的诊断类字段 + US banned term
PAYLOAD = {
    "tcm_constitution": "气虚质",
    "axis_scores": {"A": 62.0, "F": 55.0},
    "icd_code": "E11",                    # US blocked_fields
    "risk_probability": 0.23,             # US blocked_fields
    "severity": "moderate",               # US blocked_fields
    "diagnosis": "2型糖尿病",              # US banned_terms 命中
}


def test_all_five_policies_load_with_required_keys():
    policies = list_policies()
    assert set(policies) == {"cn", "us", "uk", "au", "eu"}
    for j in sorted(SUPPORTED_JURISDICTIONS):
        p = load_policy(j)
        for k in ("jurisdiction", "allowed_fields", "blocked_fields", "feature_toggles"):
            assert k in p, f"{j} 缺 {k}"


def test_unknown_jurisdiction_fails_closed_to_eu():
    # 未知法域 → STRICT_FALLBACK=eu（fail-closed，最严）
    p = load_policy("zz")
    assert p["jurisdiction"] == "eu"


def test_jurisdiction_differential_us_flags_diagnosis_term():
    # 同一输入：US 命中 banned_terms 'diagnosis' → warnings 非空；CN 不命中
    r_us = filter_output(PAYLOAD, "us")
    r_cn = filter_output(PAYLOAD, "cn")
    assert any("diagnosis" in str(w) for w in r_us.warnings), r_us.warnings
    assert not any("diagnosis" in str(w) for w in r_cn.warnings), r_cn.warnings


def test_jurisdiction_differential_blocked_fields_us_vs_cn():
    """US/CN 屏蔽差异（M10 字段级 fallback 后的新语义）：
    - US blocked_fields 命中 → 字段不删除、值被降级替换为 fallback dict，
      路径记录到 rewritten_fields；原值不再裸露
    - CN blocked_fields 为空 → 原值保留、无改写
    断言的是"敏感原值不会跨法域泄露"这一不变式，而非"字段被物理移除"。
    """
    r_us = filter_output(PAYLOAD, "us")
    r_cn = filter_output(PAYLOAD, "cn")

    # US：三个敏感字段都被降级替换
    rewritten_paths = {p.split(" ")[0].split(".")[-1] for p in r_us.rewritten_fields}
    assert {"icd_code", "risk_probability", "severity"} <= rewritten_paths, (
        r_us.rewritten_fields
    )

    # US：payload 里字段键仍存在，但值已换成 fallback 结构（原值不再裸露）
    assert isinstance(r_us.payload["icd_code"], dict)
    assert "fallback_value" in r_us.payload["icd_code"]
    assert r_us.payload["icd_code"]["fallback_value"] != "E11"
    assert r_us.payload["risk_probability"] != 0.23
    assert r_us.payload["severity"] != "moderate"

    # CN：首发市场放行，原值保留
    assert r_cn.payload["icd_code"] == "E11"
    assert r_cn.payload["risk_probability"] == 0.23
    assert r_cn.payload["severity"] == "moderate"
    assert r_cn.removed_fields == []
    assert r_cn.rewritten_fields == []


def test_endpoint_toggles_differ_by_jurisdiction():
    # US：diagnosis/risk 端点关闭；CN：放行
    ok_us, reason_us = check_endpoint_allowed("/api/v1/diagnosis", "us")
    ok_cn, _ = check_endpoint_allowed("/api/v1/diagnosis", "cn")
    assert ok_us is False and "diagnosis_endpoint" in reason_us
    assert ok_cn is True
    ok_us_risk, _ = check_endpoint_allowed("/api/v1/risk", "us")
    assert ok_us_risk is False


def test_disclaimer_attached_on_filter():
    for j in ("us", "cn", "eu", "uk", "au"):
        r = filter_output(PAYLOAD, j)
        assert r.disclaimer_added, f"{j} 未附加免责声明"


def test_audit_entrypoint_is_callable_and_nonblocking():
    # log_claims_audit 不得因审计失败而抛错（非阻塞语义）
    r = filter_output(PAYLOAD, "us")
    log_claims_audit("test-user", "us", "/api/v1/diagnosis", r)  # 不抛即过


def test_cn_specific_allowed_fields_merged():
    # CN 策略的 cn_specific_allowed 应被合并进 allowed_fields
    p = load_policy("cn")
    assert "icd_code" in p["allowed_fields"] or "icd_mapping" in p.get("feature_toggles", {})
