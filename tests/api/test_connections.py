"""数据连接 API 测试"""
import pytest


async def _register_and_login(client, user_data):
    """注册并登录，返回 (token, user_id)"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    return token, user_id


@pytest.mark.asyncio
async def test_add_connection(client, test_user_data):
    """注册->登录->调用 POST /api/v1/connections 添加华为健康连接"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/connections/",
        json={
            "source_type": "huawei_health",
            "access_token": "fake_huawei_token_123",
            "config": {"sync_interval": "daily"},
        },
        headers=headers,
    )

    assert resp.status_code == 201, f"添加连接失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["source_type"] == "huawei_health"
    assert data["data"]["is_active"] is True


@pytest.mark.asyncio
async def test_list_connections(client, test_user_data):
    """添加后列出连接"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 先添加两个连接
    for source in ["huawei_health", "apple_health"]:
        resp = await client.post(
            "/api/v1/connections/",
            json={"source_type": source, "access_token": f"token_{source}"},
            headers=headers,
        )
        assert resp.status_code == 201

    # 列出连接
    list_resp = await client.get("/api/v1/connections/", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["success"] is True
    assert list_data["meta"]["total"] == 2
    source_types = [item["source_type"] for item in list_data["data"]]
    assert "huawei_health" in source_types
    assert "apple_health" in source_types


@pytest.mark.asyncio
async def test_delete_connection(client, test_user_data):
    """添加后删除连接"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 添加连接
    add_resp = await client.post(
        "/api/v1/connections/",
        json={"source_type": "xiaomi_health", "access_token": "fake_token"},
        headers=headers,
    )
    assert add_resp.status_code == 201
    conn_id = add_resp.json()["data"]["id"]

    # 删除连接
    del_resp = await client.delete(
        f"/api/v1/connections/{conn_id}", headers=headers
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # 再次列出，应为空
    list_resp = await client.get("/api/v1/connections/", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_add_invalid_source_type(client, test_user_data):
    """添加不支持的 source_type 应返回错误"""
    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/connections/",
        json={"source_type": "fitbit", "access_token": "fake_token"},
        headers=headers,
    )

    assert resp.status_code == 400
    assert "Unsupported source_type" in resp.json()["detail"]