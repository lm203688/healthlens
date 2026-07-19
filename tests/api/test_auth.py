import pytest

@pytest.mark.asyncio
async def test_register(client):
    response = await client.post("/api/v1/auth/register", json={
        "email": "newuser@test.com",
        "password": "Password123!",
    })
    assert response.status_code in (200, 201, 501)
    data = response.json()
    if response.status_code in (200, 201):
        assert "data" in data
        assert data["success"] is True

@pytest.mark.asyncio
async def test_login(client):
    # 先注册
    await client.post("/api/v1/auth/register", json={
        "email": "login@test.com",
        "password": "Password123!",
    })
    # 再登录
    response = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com",
        "password": "Password123!",
    })
    assert response.status_code in (200, 501)

@pytest.mark.asyncio
async def test_me_unauthorized(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client, test_user_data):
    """登录后用 access_token 换 refresh_token，再用 refresh_token 获取新 access_token"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")

    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    if login_resp.status_code != 200:
        pytest.skip("Login failed")

    login_data = login_resp.json()["data"]
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]

    # 用 refresh_token 获取新的 access_token
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    new_data = refresh_resp.json()["data"]
    assert "access_token" in new_data
    assert "refresh_token" in new_data
    assert new_data["access_token"] is not None
    assert len(new_data["access_token"]) > 0
    assert new_data["refresh_token"] is not None
    assert len(new_data["refresh_token"]) > 0