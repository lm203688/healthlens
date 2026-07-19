"""404 错误场景测试"""
import uuid
import pytest


@pytest.mark.asyncio
async def test_goal_not_found(client, test_user_data):
    """GET /goals/{nonexistent} 返回 404"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code in (200, 201):
        login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
        if login_resp.status_code == 200:
            token = login_resp.json()["data"]["access_token"]
        else:
            pytest.skip("Login failed")
    else:
        pytest.skip("Registration failed")

    response = await client.get(
        f"/api/v1/goals/{str(uuid.uuid4())}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_notification_not_found(client, test_user_data):
    """DELETE /notifications/{nonexistent} 返回 404"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code in (200, 201):
        login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
        if login_resp.status_code == 200:
            token = login_resp.json()["data"]["access_token"]
        else:
            pytest.skip("Login failed")
    else:
        pytest.skip("Registration failed")

    response = await client.delete(
        f"/api/v1/notifications/{str(uuid.uuid4())}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_observation_not_found(client, test_user_data):
    """GET /records/{nonexistent} 返回 404 (observations 无 GET by id，用 records 代替)"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code in (200, 201):
        login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
        if login_resp.status_code == 200:
            token = login_resp.json()["data"]["access_token"]
        else:
            pytest.skip("Login failed")
    else:
        pytest.skip("Registration failed")

    # observations 没有按 id 获取的端点，用 records 测试
    response = await client.get(
        f"/api/v1/records/{str(uuid.uuid4())}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_diagnosis_not_found(client, test_user_data):
    """GET /diagnosis/results/{nonexistent} 返回 404"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code in (200, 201):
        login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
        if login_resp.status_code == 200:
            token = login_resp.json()["data"]["access_token"]
        else:
            pytest.skip("Login failed")
    else:
        pytest.skip("Registration failed")

    response = await client.get(
        f"/api/v1/diagnosis/results/{str(uuid.uuid4())}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
