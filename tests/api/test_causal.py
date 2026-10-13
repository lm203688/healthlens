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
