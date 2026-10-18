"""Observations API 测试 - POST 创建和批量创建"""
import pytest
from httpx import AsyncClient
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_create_single_observation(client, test_user_data):
    """测试创建单条健康指标"""
    # 注册登录
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建指标
    payload = {
        "loinc_code": "2345-7",
        "loinc_name": "Glucose [Mass/volume] in Blood",
        "value_numeric": 5.6,
        "value_unit": "mmol/L",
        "reference_range_low": 3.9,
        "reference_range_high": 6.1,
        "source": "manual",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post("/api/v1/observations/", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["loinc_code"] == "2345-7"
    assert data["value_numeric"] == 5.6
    assert data["source"] == "manual"

    # 列表里能看到，且 is_abnormal 为 False（5.6 在 3.9-6.1 范围内）
    list_resp = await client.get("/api/v1/observations/", headers=headers)
    assert list_resp.status_code == 200
    observations = list_resp.json()["data"]
    matched = [o for o in observations if o["loinc_code"] == "2345-7"]
    assert len(matched) >= 1
    assert matched[0]["is_abnormal"] is False


@pytest.mark.asyncio
async def test_batch_create_observations(client, test_user_data):
    """测试批量创建健康指标"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "items": [
            {
                "loinc_code": "2093-3",
                "loinc_name": "Cholesterol",
                "value_numeric": 5.8,
                "value_unit": "mmol/L",
                "reference_range_low": 2.8,
                "reference_range_high": 5.2,
                "recorded_at": now,
            },
            {
                "loinc_code": "2085-9",
                "loinc_name": "Triglycerides",
                "value_numeric": 1.9,
                "value_unit": "mmol/L",
                "reference_range_low": 0.3,
                "reference_range_high": 1.7,
                "recorded_at": now,
            },
        ]
    }
    resp = await client.post("/api/v1/observations/batch", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert len(data) == 2
    assert resp.json()["meta"]["count"] == 2

    # 列表能查到
    list_resp = await client.get("/api/v1/observations/", headers=headers)
    assert list_resp.json()["meta"]["total"] >= 2
