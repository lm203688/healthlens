import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_summary(client, test_user_data):
    """测试健康摘要报告"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")

    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    if login_resp.status_code != 200:
        pytest.skip("Login failed")
    token = login_resp.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/reports/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "user_id" in data
    assert "analysis" in data
    assert data["analysis"]["total_items"] == 0  # 新用户无数据


@pytest.mark.asyncio
async def test_fhir_export(client, test_user_data):
    """测试 FHIR 导出"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")

    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    if login_resp.status_code != 200:
        pytest.skip("Login failed")
    token = login_resp.json()["data"]["access_token"]

    response = await client.get(
        "/api/v1/reports/fhir",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    bundle = response.json()["data"]
    assert bundle["resourceType"] == "Bundle"
    assert "entry" in bundle
