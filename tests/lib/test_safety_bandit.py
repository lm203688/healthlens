"""安全约束 LinUCB 测试 —— L1-3

覆盖：
- SafetyMask：十八反 / 妊娠禁忌 / 危急值 / 合法组合 / 缺 intervention
- LinUCB：简单线性问题收敛 / Q 值单调 / 未知维度 / 负奖励 / 与随机对比
- SafetyBanditPolicy：3 动作 1 屏蔽 / 全屏蔽 / mask_log / reward_expected /
  端到端迭代
- build_policy / 默认 feature builder

wellness 边界：不出现诊断/治疗/患者/医疗词汇。
"""
from __future__ import annotations

import math
import random
from typing import Any

import pytest

from app.lib.safety_bandit import (
    SafetyMask,
    SafetyDecision,
    LinUCB,
    SafetyBanditPolicy,
    BanditStepResult,
    build_policy,
    _default_feature_builder,
)


# ---------------------------------------------------------------------------
# SafetyMask —— 配伍禁忌
# ---------------------------------------------------------------------------


def test_safety_mask_eight_antagonisms_gancao_gansui():
    """十八反：甘草 + 甘遂 → 屏蔽，reasons 含 '十八反'。"""
    mask = SafetyMask()
    d = mask.check(
        candidate_action={"intervention": "herb_combo", "herbs": ["甘草", "甘遂"]},
        user_context={"jurisdiction": "cn"},
    )
    assert d.allowed is False
    assert any("十八反" in r for r in d.reasons)


def test_safety_mask_eight_antagonisms_gancao_haizao():
    """十八反：甘草 + 海藻。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "combo", "herbs": ["甘草", "海藻"]},
        {},
    )
    assert d.allowed is False
    assert any("十八反" in r for r in d.reasons)


def test_safety_mask_pregnancy_caution_danggui():
    """妊娠禁忌（慎用）：妊娠 + 当归 → 屏蔽。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "herb_test", "herbs": ["当归"]},
        {"pregnancy": True},
    )
    assert d.allowed is False
    assert any("妊娠" in r for r in d.reasons)


def test_safety_mask_pregnancy_prohibited_banzha():
    """妊娠禁忌（禁用）：妊娠 + 半夏 → 屏蔽。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "herb_test", "herbs": ["半夏"]},
        {"pregnancy": True},
    )
    assert d.allowed is False
    assert any("妊娠" in r for r in d.reasons)


def test_safety_mask_critical_value_high_glucose():
    """危急值：血糖 25.0 > 22.2 → 屏蔽。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "diet_test"},
        {"biomarkers": {"blood_glucose": 25.0}},
    )
    assert d.allowed is False
    assert any("危急值" in r or "critical_value" in r for r in d.reasons)


def test_safety_mask_critical_value_high_potassium():
    """危急值：血钾 7.0 > 6.2 → 屏蔽。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "supp"},
        {"biomarkers": {"potassium": 7.0}},
    )
    assert d.allowed is False


def test_safety_mask_critical_value_in_action():
    """危急值在 candidate_action.biomarkers 里也触发。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "supp", "biomarkers": {"potassium": 7.0}},
        {},
    )
    assert d.allowed is False


def test_safety_mask_legal_combination():
    """合法组合：无禁忌的 herbs + 非妊娠 → allowed=True。"""
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "diet", "herbs": ["枸杞", "黄芪"]},
        {"pregnancy": False, "jurisdiction": "cn"},
    )
    assert d.allowed is True
    assert d.reasons == []


def test_safety_mask_missing_intervention_fail_loud():
    """缺 intervention → allowed=False + reasons 含 [policy]。"""
    mask = SafetyMask()
    d = mask.check({"herbs": ["枸杞"]}, {})
    assert d.allowed is False
    assert any("intervention" in r for r in d.reasons)


def test_safety_mask_empty_action():
    """完全空的 candidate_action → 屏蔽。"""
    mask = SafetyMask()
    d = mask.check({}, {})
    assert d.allowed is False


def test_safety_mask_as_dict_structure():
    mask = SafetyMask()
    d = mask.check(
        {"intervention": "combo", "herbs": ["甘草", "甘遂"]},
        {},
    )
    dd = d.as_dict()
    assert dd["allowed"] is False
    assert isinstance(dd["reasons"], list)
    assert isinstance(dd["findings"], list)
    assert len(dd["findings"]) > 0


def test_safety_mask_batch_check():
    mask = SafetyMask()
    actions = [
        {"intervention": "a1", "herbs": ["甘草", "甘遂"]},
        {"intervention": "a2", "herbs": ["枸杞"]},
    ]
    results = mask.batch_check(actions, {"jurisdiction": "cn"})
    assert len(results) == 2
    assert results[0].allowed is False
    assert results[1].allowed is True


def test_safety_mask_strict_moderate_blocks():
    """strict=True（默认）：moderate 也屏蔽。strict=False：moderate 放行。"""
    # 妊娠慎用（moderate）
    action = {"intervention": "herb", "herbs": ["当归"]}
    ctx = {"pregnancy": True}
    strict = SafetyMask(strict=True).check(action, ctx)
    non_strict = SafetyMask(strict=False).check(action, ctx)
    # 妊娠慎用是 moderate；strict=True 屏蔽
    assert strict.allowed is False
    # strict=False 只屏蔽 high
    # 当归仅命中妊娠慎用（moderate），无 high → 放行
    assert non_strict.allowed is True


# ---------------------------------------------------------------------------
# LinUCB
# ---------------------------------------------------------------------------


def test_linucb_simple_linear_converges_to_best():
    """3 臂，特征 [1,0],[0,1],[1,1]，真奖励线性可分 → 100 步后选最优。"""
    rng = random.Random(42)
    bandit = LinUCB(d=2, alpha=0.5)
    arms = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    # 真奖励：arm0=1.0, arm1=0.5, arm2=2.0 → 最优 arm2
    true_rewards = {0: 1.0, 1: 0.5, 2: 2.0}
    last_pick = -1
    for _ in range(100):
        qs = [bandit.predict(a) for a in arms]
        pick = max(range(3), key=lambda i: qs[i])
        bandit.update(arms[pick], true_rewards[pick])
        last_pick = pick
    # 最后 20 步里 arm2 应占多数（收敛信号）
    picks = []
    for _ in range(20):
        qs = [bandit.predict(a) for a in arms]
        picks.append(max(range(3), key=lambda i: qs[i]))
    assert picks.count(2) >= 15  # 至少 15/20 选最优臂


def test_linucb_q_monotonic_after_positive_update():
    """同一特征 + 正奖励更新后 Q 应升高（相对更新前）。"""
    bandit = LinUCB(d=2, alpha=0.5)
    feat = [1.0, 0.0]
    q_before = bandit.predict(feat)
    bandit.update(feat, 5.0)  # 大幅正奖励
    q_after = bandit.predict(feat)
    # 更新后点估计升高，Q 应升高（尽管 UCB 项可能下降，但正奖励足够大）
    assert q_after > q_before


def test_linucb_q_predict_all():
    bandit = LinUCB(d=2, alpha=0.5)
    arms = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    qs = bandit.predict_all(arms)
    assert len(qs) == 3
    for q in qs:
        assert isinstance(q, float)


def test_linucb_unknown_dim_raises():
    bandit = LinUCB(d=2)
    with pytest.raises(ValueError):
        bandit.predict([1.0])  # 长度不匹配
    with pytest.raises(ValueError):
        bandit.predict([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        bandit.update([1.0], 1.0)


def test_linucb_negative_reward_update():
    """负奖励也能更新，不崩溃。"""
    bandit = LinUCB(d=2, alpha=0.5)
    feat = [1.0, 1.0]
    q_before = bandit.predict(feat)
    bandit.update(feat, -3.0)
    q_after = bandit.predict(feat)
    # 更新后 Q 应下降（负奖励降低点估计）
    assert q_after < q_before


def test_linucb_state():
    bandit = LinUCB(d=3, alpha=1.5, ridge=2.0)
    s = bandit.state()
    assert s["d"] == 3
    assert s["alpha"] == 1.5
    assert s["n_updates"] == 0
    bandit.update([0.1, 0.2, 0.3], 1.0)
    s = bandit.state()
    assert s["n_updates"] == 1


def test_linucb_invalid_d_raises():
    with pytest.raises(ValueError):
        LinUCB(d=0)
    with pytest.raises(ValueError):
        LinUCB(d=-1)


def test_linucb_invalid_alpha_raises():
    with pytest.raises(ValueError):
        LinUCB(d=2, alpha=-1.0)


def test_linucb_beats_random_cumulative():
    """LinUCB 累积奖励应显著优于随机选择。"""
    arms = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    true_rewards = [1.0, 0.5, 2.0]  # 最优 arm2

    # LinUCB
    bandit = LinUCB(d=2, alpha=0.5)
    uc_cum = 0.0
    for _ in range(100):
        qs = [bandit.predict(a) for a in arms]
        pick = max(range(3), key=lambda i: qs[i])
        r = true_rewards[pick]
        uc_cum += r
        bandit.update(arms[pick], r)

    # Random
    rng = random.Random(42)
    rand_cum = 0.0
    for _ in range(100):
        pick = rng.randrange(3)
        rand_cum += true_rewards[pick]

    assert uc_cum > rand_cum * 1.15  # LinUCB 至少优 15%


def test_linucb_predict_initial_positive():
    """初始状态（未更新）Q 应 > 0（UCB 探索项为正）。"""
    bandit = LinUCB(d=2, alpha=1.0)
    q = bandit.predict([1.0, 1.0])
    assert q > 0


def test_linucb_ridge_affects_initial():
    """ridge 越大 → A 初值越对角 → 初始 UCB 越小。"""
    b1 = LinUCB(d=2, alpha=1.0, ridge=1.0)
    b2 = LinUCB(d=2, alpha=1.0, ridge=5.0)
    q1 = b1.predict([1.0, 1.0])
    q2 = b2.predict([1.0, 1.0])
    # ridge 大 → A 初值 (1+5)I = 6I → A_inv = (1/6)I → UCB = α*sqrt(x^T*(1/6)I*x)
    # ridge 小 → A 初值 2I → A_inv = (1/2)I → UCB 更大
    assert q1 > q2


# ---------------------------------------------------------------------------
# SafetyBanditPolicy
# ---------------------------------------------------------------------------


def test_policy_three_actions_one_masked():
    """3 动作，其中 1 个被 mask → 只能在合法 2 个中选。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {"pregnancy": False, "medications": [], "jurisdiction": "cn"}
    actions = [
        {"intervention": "diet", "dose": 1.0},
        {"intervention": "herb_combo", "herbs": ["甘草", "甘遂"]},  # 被屏蔽
        {"intervention": "exercise", "dose": 1.0},
    ]
    r = policy.step(ctx, actions)
    assert r.action is not None
    # 选中的不能是被屏蔽的那个
    assert r.action.get("intervention") in ("diet", "exercise")
    # 被屏蔽动作的 q 应为 -inf
    assert math.isinf(r.q_values["herb_combo"]) and r.q_values["herb_combo"] < 0


def test_policy_all_masked_returns_none():
    """全部被屏蔽 → action=None, chosen_index=None。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {"pregnancy": True, "medications": [], "jurisdiction": "cn"}
    actions = [
        {"intervention": "h1", "herbs": ["当归"]},   # 妊娠慎用 → 屏蔽
        {"intervention": "h2", "herbs": ["半夏"]},   # 妊娠禁用 → 屏蔽
    ]
    r = policy.step(ctx, actions)
    assert r.action is None
    assert r.chosen_index is None
    assert math.isinf(r.reward_expected) and r.reward_expected < 0


def test_policy_mask_log_records_masked():
    """mask_log 记录所有动作的 SafetyDecision。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {"pregnancy": False, "jurisdiction": "cn"}
    actions = [
        {"intervention": "a1", "herbs": ["甘草", "甘遂"]},
        {"intervention": "a2", "herbs": ["枸杞"]},
    ]
    r = policy.step(ctx, actions)
    assert len(r.mask_log) == 2
    assert r.mask_log[0].allowed is False
    assert r.mask_log[1].allowed is True


def test_policy_reward_expected_is_q_value():
    """reward_expected = 选中动作的 Q 值。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {"pregnancy": False, "jurisdiction": "cn"}
    actions = [
        {"intervention": "a1", "dose": 1.0},
        {"intervention": "a2", "dose": 2.0},
    ]
    r = policy.step(ctx, actions)
    assert r.action is not None
    aid = r.action["intervention"]
    assert r.reward_expected == r.q_values[aid]
    assert r.chosen_index is not None


def test_policy_end_to_end_5_steps():
    """SafetyMask + LinUCB 端到端：5 步迭代不崩溃。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {
        "pregnancy": False,
        "medications": [],
        "jurisdiction": "cn",
        "biomarkers": {"potassium": 4.5},
    }
    actions = [
        {"intervention": "diet", "dose": 1.0},
        {"intervention": "herb_bad", "herbs": ["甘草", "甘遂"]},
        {"intervention": "exercise", "dose": 1.0},
        {"intervention": "supp", "dose": 0.5},
    ]
    for _ in range(5):
        r = policy.step(ctx, actions)
        assert r.action is not None
        # 选中的不能被屏蔽
        assert r.mask_log[r.chosen_index].allowed is True
        # 更新一次（模拟 reward 回传）
        policy.update(r.action, reward=1.0)


def test_policy_empty_candidates_returns_none():
    """空候选 → action=None, q_values={}, mask_log=[]。"""
    policy = build_policy(alpha=1.0, d=5)
    r = policy.step({}, [])
    assert r.action is None
    assert r.q_values == {}
    assert r.mask_log == []
    assert math.isinf(r.reward_expected) and r.reward_expected > 0


def test_policy_chosen_index_matches_action():
    """chosen_index 应指向候选列表里的选中动作。"""
    policy = build_policy(alpha=1.0, d=5, strict=True)
    ctx = {"pregnancy": False, "jurisdiction": "cn"}
    actions = [
        {"intervention": "a1"},
        {"intervention": "a2"},
        {"intervention": "a3"},
    ]
    r = policy.step(ctx, actions)
    assert r.chosen_index is not None
    assert r.action is not None
    assert r.action == actions[r.chosen_index]


def test_policy_custom_feature_builder():
    """自定义 feature_builder 被正确使用。"""
    calls = []

    def builder(ctx, action):
        calls.append(action.get("intervention"))
        return [1.0, 2.0, 3.0]

    policy = SafetyBanditPolicy(
        bandit=LinUCB(d=3),
        mask=SafetyMask(),
        feature_builder=builder,
    )
    ctx = {"jurisdiction": "cn"}
    actions = [{"intervention": "x1", "dose": 1.0}]
    r = policy.step(ctx, actions)
    assert r.action is not None
    assert "x1" in calls


def test_policy_action_id_key_custom():
    """action_id_key 可自定义：q_values 以指定 key 索引。"""
    policy = build_policy(alpha=1.0, d=5)
    ctx = {"jurisdiction": "cn"}
    # intervention 保留（mask 需要），同时用 name 作为 id key
    actions = [
        {"intervention": "a1", "name": "name_a1", "dose": 1.0},
        {"intervention": "a2", "name": "name_a2", "dose": 2.0},
    ]
    r = policy.step(ctx, actions, action_id_key="name")
    assert r.action is not None
    # q_values 应以 name 为 key
    assert "name_a1" in r.q_values
    assert "name_a2" in r.q_values


def test_policy_status():
    policy = build_policy(alpha=1.5, d=5)
    s = policy.status()
    assert s["not_clinical"] is True
    assert s["bandit"]["d"] == 5
    assert s["n_actions_seen"] == 0
    policy.update({"intervention": "x"}, 1.0)
    s = policy.status()
    assert s["n_actions_seen"] == 1


def test_bandit_step_result_as_dict():
    r = BanditStepResult(
        action={"intervention": "a1"},
        reward_expected=0.5,
        q_values={"a1": 0.5, "a2": -math.inf},
        mask_log=[],
        chosen_index=0,
    )
    d = r.as_dict()
    assert d["action"] == {"intervention": "a1"}
    assert d["reward_expected"] == 0.5
    assert d["chosen_index"] == 0
    assert d["not_clinical"] is True
    assert "disclaimer" in d


def test_bandit_step_result_as_dict_infinite():
    """reward_expected = -inf 时 as_dict 保留 inf。"""
    r = BanditStepResult(
        action=None,
        reward_expected=-math.inf,
        q_values={"a1": -math.inf},
        mask_log=[],
        chosen_index=None,
    )
    d = r.as_dict()
    assert d["action"] is None
    assert d["reward_expected"] == -math.inf
    assert d["q_values"]["a1"] == -math.inf


def test_default_feature_builder_5_dim():
    """默认 feature_builder 产出 5 维向量。"""
    ctx = {"pregnancy": True, "medications": ["a", "b"], "jurisdiction": "cn"}
    action = {"intervention": "test", "dose": 50.0}
    feat = _default_feature_builder(ctx, action)
    assert len(feat) == 5
    assert feat[2] == 1.0  # pregnancy=1
    assert feat[3] == 0.2  # 2/10
    assert feat[4] == 1.0  # cn=1


def test_build_policy_returns_policy():
    p = build_policy(alpha=1.0, d=5, strict=True)
    assert isinstance(p, SafetyBanditPolicy)
    assert isinstance(p.bandit, LinUCB)
    assert isinstance(p.mask, SafetyMask)


def test_policy_update_increments_bandit_updates():
    policy = build_policy(alpha=1.0, d=5)
    assert policy.bandit.n_updates == 0
    policy.update({"intervention": "x", "dose": 1.0}, 1.0)
    assert policy.bandit.n_updates == 1
    policy.update({"intervention": "y", "dose": 1.0}, 2.0)
    assert policy.bandit.n_updates == 2
