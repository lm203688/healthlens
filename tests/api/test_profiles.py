"""Profiles API 测试 - 健康档案 CRUD"""
import pytest
from httpx import AsyncClient
from datetime import date


@pytest.mark.asyncio
async def test_create_and_get_profile(client, test_user_data):
    """测试创建和获取健康档案"""
    # 注册登录
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 首次获取 - 应为 404
    get_resp = await client.get("/api/v1/profiles/", headers=headers)
    assert get_resp.status_code == 404

    # 创建档案
    create_payload = {
        "name": "张三",
        "gender": "male",
        "birth_date": "1990-01-15",
        "blood_type": "A+",
        "height_cm": 175.0,
        "weight_kg": 70.0,
    }
    create_resp = await client.post("/api/v1/profiles/", json=create_payload, headers=headers)
    assert create_resp.status_code == 201
    data = create_resp.json()["data"]
    assert data["name"] == "张三"
    assert data["gender"] == "male"

    # 重复创建 - 应 409
    dup_resp = await client.post("/api/v1/profiles/", json=create_payload, headers=headers)
    assert dup_resp.status_code == 409

    # 获取档案
    get_resp = await client.get("/api/v1/profiles/", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["name"] == "张三"


@pytest.mark.asyncio
async def test_update_profile(client, test_user_data):
    """测试更新健康档案"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 先创建
    create_resp = await client.post("/api/v1/profiles/", json={
        "name": "李四",
        "gender": "female",
        "blood_type": "O",
    }, headers=headers)
    assert create_resp.status_code == 201

    # 部分更新
    update_resp = await client.put("/api/v1/profiles/", json={
        "height_cm": 162.0,
        "weight_kg": 55.0,
    }, headers=headers)
    assert update_resp.status_code == 200
    data = update_resp.json()["data"]
    assert data["height_cm"] == 162.0
    assert data["name"] == "李四"  # 未更新的字段保持不变
