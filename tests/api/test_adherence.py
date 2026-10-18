"""用药依从性 API 测试"""
import pytest
from datetime import datetime, timezone, timedelta


@pytest.mark.asyncio
async def test_create_adherence_plan(client, test_user_data):
    """测试创建服药计划"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "medication_name": "阿司匹林",
        "prescribed_dose": "100mg",
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post("/api/v1/adherence", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["medication_name"] == "阿司匹林"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_record_medication_intake(client, test_user_data):
    """测试记录服药"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建计划
    create_resp = await client.post("/api/v1/adherence", json={
        "medication_name": "二甲双胍",
        "prescribed_dose": "500mg",
        "scheduled_at": datetime.now(timezone.utc).isoformat(),
    }, headers=headers)
    record_id = create_resp.json()["data"]["id"]

    # 记录服药
    resp = await client.put(f"/api/v1/adherence/{record_id}", json={
        "status": "taken",
        "note": "饭后服用",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "taken"
    assert data["taken_at"] is not None


@pytest.mark.asyncio
async def test_adherence_stats(client, test_user_data, db_session):
    """测试依从性统计"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = login_resp.json()["data"]["user"]["id"]

    # 直接插入多条记录
    from app.models.medication_adherence import MedicationAdherence
    import uuid
    now = datetime.now(timezone.utc)

    for i in range(10):
        record = MedicationAdherence(
            id=str(uuid.uuid4()),
            user_id=user_id,
            medication_name="测试药物",
            scheduled_at=now - timedelta(days=i),
            status="taken" if i < 8 else "missed",  # 8次按时，2次漏服
            taken_at=now - timedelta(days=i) if i < 8 else None,
        )
        db_session.add(record)
    await db_session.commit()

    resp = await client.get("/api/v1/adherence/stats/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_planned"] >= 10
    assert data["total_taken"] >= 8
    assert data["total_missed"] >= 2
    # 依从率 = 8 / (8+2) = 80%
    assert data["adherence_rate"] == 80.0


@pytest.mark.asyncio
async def test_list_adherence(client, test_user_data):
    """测试列出服药记录"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建几条记录
    for i in range(3):
        await client.post("/api/v1/adherence", json={
            "medication_name": f"药物{i}",
            "scheduled_at": (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(),
        }, headers=headers)

    resp = await client.get("/api/v1/adherence", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 3
