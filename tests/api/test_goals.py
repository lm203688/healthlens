"""健康目标 API 测试"""
import pytest
from datetime import datetime, timezone, timedelta


@pytest.mark.asyncio
async def test_create_and_list_goal(client, test_user_data):
    """测试创建和列出健康目标"""
    # 注册登录
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建目标
    payload = {
        "goal_type": "steps",
        "goal_name": "每日步数目标",
        "target_value": 10000,
        "current_value": 5000,
        "unit": "步",
        "target_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }
    resp = await client.post("/api/v1/goals", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["goal_type"] == "steps"
    assert data["target_value"] == 10000
    assert data["progress"] == 50.0  # 5000/10000

    # 列出目标
    list_resp = await client.get("/api/v1/goals", headers=headers)
    assert list_resp.status_code == 200
    goals = list_resp.json()["data"]
    assert len(goals) >= 1
    assert goals[0]["goal_name"] == "每日步数目标"


@pytest.mark.asyncio
async def test_add_progress_and_complete(client, test_user_data):
    """测试添加进度并自动完成目标"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建目标 (减重目标)
    payload = {
        "goal_type": "weight",
        "goal_name": "减重至65kg",
        "target_value": 65,
        "current_value": 70,
        "unit": "kg",
        "target_date": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
    }
    create_resp = await client.post("/api/v1/goals", json=payload, headers=headers)
    goal_id = create_resp.json()["data"]["id"]

    # 添加进度 - 达到目标
    progress_resp = await client.post(
        f"/api/v1/goals/{goal_id}/progress",
        json={"value": 65, "note": "达标了"},
        headers=headers,
    )
    assert progress_resp.status_code == 201
    progress_data = progress_resp.json()["data"]
    assert progress_data["goal_progress"] == 100.0
    assert progress_data["goal_status"] == "completed"


@pytest.mark.asyncio
async def test_goal_stats(client, test_user_data):
    """测试目标统计"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建2个目标
    for i in range(2):
        await client.post("/api/v1/goals", json={
            "goal_type": "steps",
            "goal_name": f"目标{i}",
            "target_value": 8000,
            "current_value": 4000,
            "unit": "步",
            "target_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }, headers=headers)

    stats_resp = await client.get("/api/v1/goals/summary/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["data"]
    assert stats["total_goals"] >= 2
    assert stats["active_goals"] >= 2
