"""因果推演 API 测试（S2-1，2026-10-13）

覆盖：结构/敏感性/杠杆（公开）+ 反事实/校准/报告（需登录）+ 鉴权 + fail-loud 校验。
"""
import pytest


# ---------------------------------------------------------------------------
# 结构类端点（公开）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scm_structure_public(client):
    resp = await client.get("/api/v1/causal/scm")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 8                       # 八轴内生节点
    assert len(data["edges"]) >= 1                       # 有向耦合边
    assert len(data["interventions"]) == 7               # 生活方式杠杆
    assert len(data["unobserved_confounders"]) >= 1      # 被承认的未观测混淆
    assert data["assumptions"]


@pytest.mark.asyncio
async def test_sensitivity_public(client):
    resp = await client.get("/api/v1/causal/sensitivity")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bridges"]
    for b in data["bridges"]:
        assert b["e_value"] >= 1.0
        assert {"from", "to", "coupling", "interpretation"} <= set(b)


@pytest.mark.asyncio
async def test_levers_public(client):
    resp = await client.get("/api/v1/causal/levers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["levers"]
    assert set(body["axes"]) == set("ABCDEFGH")


# ---------------------------------------------------------------------------
# 鉴权辅助
# ---------------------------------------------------------------------------

async def _auth_headers(client, test_user_data):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    if reg.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 个性化推演端点（需登录）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_counterfactual(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 40, "F": 42},
              "levers": ["sleep_hygiene", "fasting"], "weeks": 12},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["not_clinical"] is True
    assert set(data["effect_per_axis"]) == set("ABCDEFGH")
    assert isinstance(data["wellness_index_effect"], (int, float))
    assert data["disclaimer"]


# ---------------------------------------------------------------------------
# 反事实效应的不确定区间（M07 置信区间）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_counterfactual_returns_effect_ci(client, test_user_data):
    """/counterfactual 应输出效应的 5/95 分位带，且结构自洽。"""
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 40, "F": 42},
              "levers": ["sleep_hygiene", "fasting"], "weeks": 12},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["effect_ci_per_axis"]) == set("ABCDEFGH")
    for band in data["effect_ci_per_axis"].values():
        assert {"p5", "p95", "width", "sign_stable"} <= set(band)
        assert band["p5"] <= band["p95"]
        assert band["width"] >= 0
        assert isinstance(band["sign_stable"], bool)
    assert set(data["wellness_index_effect_ci"]) >= {"p5", "p95", "width", "sign_stable"}
    assert data["n_bootstrap"] == 200
    # 点估计必须落在区间内或紧邻边界（舍入误差范围内）
    for ax, band in data["effect_ci_per_axis"].items():
        assert band["p5"] - 0.2 <= data["effect_per_axis"][ax] <= band["p95"] + 0.2, (
            f"轴 {ax} 点估计 {data['effect_per_axis'][ax]} 偏离区间 {band}")


@pytest.mark.asyncio
async def test_no_levers_effect_ci_unstable(client, test_user_data):
    """无干预时效应为 0，区间跨 0 → sign_stable 应为 False。

    这是诚实性验证：零效应不能声称「符号稳定」，否则等于宣称「确定无效」。
    """
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 40}, "levers": [], "weeks": 12},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert abs(data["wellness_index_effect"]) < 1e-6
    assert data["wellness_index_effect_ci"]["sign_stable"] is False
    for band in data["effect_ci_per_axis"].values():
        assert band["sign_stable"] is False
        assert band["width"] < 1.0  # 无扰动时两条轨迹相同，区间应极窄


# ---------------------------------------------------------------------------
# 库层：配对 bootstrap 的统计性质
# ---------------------------------------------------------------------------

def test_effect_ci_paired_shares_perturbed_network():
    """配对不变式：actual 与 no_intervention 必须收到**同一份**扰动网络。

    这是配对 bootstrap 的语义前提——两条分支在同一参数环境下对比，
    反事实差值才有意义。若各自独立抽样，参数环境本身就成了混淆因素。

    注意：本测试**不**断言「配对带宽 < 独立带宽」。在当前 simulate() 实现下
    该断言不成立：no-intervention 分支 levers=[] 无主动驱动，桥接只在
    「上游改善 > 0.5」时传导、条件恒不满足 → 该分支对耦合扰动免疫
    （方差为 0），故效应带宽 = actual 分支带宽，配对与独立数值恒等。
    配对的价值在此实现下是**语义正确性**（同环境对比），不是带宽收窄。
    """
    import app.lib.causal_simulator as cs

    base = {"A": 40, "F": 42}
    captured = []  # 每次 simulate 调用收到的 bridges 对象
    original = cs.simulate

    def spy(baseline, levers, weeks, lever_scale, bridges=None):
        captured.append(bridges)
        return original(baseline, levers, weeks, lever_scale, bridges=bridges)

    cs.simulate = spy
    try:
        cs._effect_ci(base, ["sleep_hygiene"], 12, 1.0, n=5, seed=20261013)
    finally:
        cs.simulate = original

    # 5 轮迭代 × 2 条分支 = 10 次调用
    assert len(captured) == 10, f"应有 10 次 simulate 调用，实际 {len(captured)}"
    # 每轮内两次调用收到同一份 bridges 对象（同一标识 = 真配对）
    for i in range(0, 10, 2):
        assert captured[i] is captured[i + 1], (
            f"第 {i // 2} 轮 actual 与 no_intervention 未共享同一扰动网络")
        assert captured[i] is not None, "扰动网络不应为 None"
    # 各轮之间应是不同对象（每轮独立扰动，否则 bootstrap 无效）
    objects = {id(captured[i]) for i in range(0, 10, 2)}
    assert len(objects) == 5, f"应有 5 份独立扰动网络，实际 {len(objects)}"


def test_effect_ci_deterministic_seed():
    """固定 seed → 区间可复现；n_bootstrap=0 → 跳过区间。"""
    from app.lib.causal_simulator import counterfactual
    from app.lib.wellness_simulator import derive_baseline

    base = derive_baseline(provided={"A": 40, "F": 42})
    r1 = counterfactual(base, ["sleep_hygiene"], 12, 1.0)
    r2 = counterfactual(base, ["sleep_hygiene"], 12, 1.0)
    assert r1["effect_ci_per_axis"] == r2["effect_ci_per_axis"]
    assert r1["wellness_index_effect_ci"] == r2["wellness_index_effect_ci"]

    r0 = counterfactual(base, ["sleep_hygiene"], 12, 1.0, n_bootstrap=0)
    assert r0["effect_ci_per_axis"] == {}
    assert r0["wellness_index_effect_ci"] == {}
    assert r0["n_bootstrap"] == 0
    # 跳过区间时点估计仍正常产出
    assert set(r0["effect_per_axis"]) == set("ABCDEFGH")


def test_effect_ci_distinct_from_trajectory_ci():
    """效应区间与轨迹校准区间是两个不同的量，不可互相替代。

    结构区分（这是真实且稳定的不变式）：效应区间含 ``sign_stable`` 字段，
    轨迹区间不含——前者回答「干预有没有用」，后者回答「干预后终值在哪」。

    **幅度关系的诚实说明**：在当前 ``simulate()`` 实现下，两宽度**精确相等**，
    而非「效应远小于轨迹」。原因：no-intervention 分支 ``levers=[]`` 无主动
    驱动，桥接只在「上游改善 > 0.5」时传导、该条件恒不满足 → 该分支对耦合
    扰动免疫（终值为常数）→ 效应带宽 = actual 分支带宽 = 轨迹带宽。

    因此本测试**不**断言幅度大小，只断言结构区分与相等的数学一致性
    （若日后 simulate 让 no-intervention 分支随扰动波动，相等关系会变，
    届时需同步更新本测试——这正是把结构事实钉死的价值）。
    """
    from app.lib.causal_simulator import calibrate, counterfactual
    from app.lib.wellness_simulator import derive_baseline

    base = derive_baseline(provided={"A": 40, "F": 42})
    cf = counterfactual(base, ["sleep_hygiene"], 12, 1.0)
    cal = calibrate(base, ["sleep_hygiene"], 12, 1.0)
    assert set(cf["effect_ci_per_axis"]) == set("ABCDEFGH")
    # 结构上可区分：效应区间带 sign_stable，轨迹区间不带
    assert "sign_stable" in cf["effect_ci_per_axis"]["A"]
    assert "sign_stable" not in cal["calibration"]["A"]
    # 语义上不同：两者度量的是不同的量（效应 vs 终值），点估计也不同
    assert cf["effect_per_axis"]["A"] != cal["calibration"]["A"]["point"]
    # 幅度：当前实现下两宽度精确相等（no-intervention 分支方差为 0）
    for ax in "ABCDEFGH":
        effect_w = cf["effect_ci_per_axis"][ax]["width"]
        traj_w = cal["calibration"][ax]["p95"] - cal["calibration"][ax]["p5"]
        assert abs(effect_w - traj_w) < 0.2, (
            f"轴 {ax}: 效应带宽 {effect_w} 与轨迹带宽 {traj_w} 应相等 "
            f"（no-intervention 分支对扰动免疫）；若不等说明 simulate 结构已变")


@pytest.mark.asyncio
async def test_calibrate(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/calibrate",
        json={"baseline": {"A": 40}, "levers": ["aerobic"], "weeks": 8},
        headers=headers,
    )
    assert resp.status_code == 200
    cal = resp.json()["calibration"]
    assert set(cal) == set("ABCDEFGH")
    for ax, band in cal.items():
        assert band["p5"] <= band["p95"]
        assert {"point", "p5", "p95"} <= set(band)


@pytest.mark.asyncio
async def test_report(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/report",
        json={"baseline": {"A": 40, "F": 42},
              "levers": ["sleep_hygiene", "fasting", "anti_inflammatory_diet"], "weeks": 12},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert {"scm", "counterfactual", "calibration", "sensitivity"} <= set(data)
    assert data["not_clinical"] is True
    assert data["disclaimer"]


@pytest.mark.asyncio
async def test_report_requires_auth(client):
    resp = await client.post("/api/v1/causal/report", json={"levers": []})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# fail-loud 校验（越界 → 400，不静默降级）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bad_axis_400(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"Z": 50}, "levers": []}, headers=headers,
    )
    assert resp.status_code == 400
    assert "未知轴" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_bad_lever_400(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 40}, "levers": ["bogus_lever"]}, headers=headers,
    )
    assert resp.status_code == 400
    assert "未知杠杆" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_out_of_range_400(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 150}, "levers": []}, headers=headers,
    )
    assert resp.status_code == 400
    assert "越界" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_weeks_out_of_range_422(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    resp = await client.post(
        "/api/v1/causal/counterfactual",
        json={"baseline": {"A": 40}, "levers": [], "weeks": 999}, headers=headers,
    )
    assert resp.status_code == 422
