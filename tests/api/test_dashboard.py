"""健康仪表盘 API 测试"""
import pytest
from datetime import datetime, timezone, date


@pytest.mark.asyncio
async def test_dashboard_overview_empty(client, test_user_data):
    """测试空仪表盘总览"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/dashboard/overview", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "summary" in data
    assert data["summary"]["recent_observations_30d"] == 0
    assert data["summary"]["active_goals"] == 0
    assert data["summary"]["unread_notifications"] == 0


@pytest.mark.asyncio
async def test_metric_trends_empty(client, test_user_data):
    """测试空指标趋势"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/dashboard/trends/8480-6", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["loinc_code"] == "8480-6"
    assert data["data_points"] == []
    assert data["stats"] == {}


@pytest.mark.asyncio
async def test_risk_assessment_without_profile(client, test_user_data):
    """测试无健康档案时触发风险评估应报错"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/dashboard/risk-assessment", headers=headers)
    assert resp.status_code == 400
    assert "健康档案" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_risk_assessment_with_profile(client, test_user_data, db_session):
    """测试有健康档案时触发风险评估"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = login_resp.json()["data"]["user"]["id"]

    # 创建健康档案 (55岁男性)
    from app.models.health_record import HealthProfile
    import uuid
    profile = HealthProfile(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name="测试用户",
        gender="male",
        birth_date=date(1970, 1, 1),  # 约55岁
        height_cm=170,
        weight_kg=75,
    )
    db_session.add(profile)
    await db_session.commit()

    # 触发风险评估
    resp = await client.post("/api/v1/dashboard/risk-assessment", headers=headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert "overall_risk_level" in data
    assert "assessments" in data
    assert len(data["assessments"]) >= 2  # diabetes + metabolic_syndrome (55岁有ascvd)


@pytest.mark.asyncio
async def test_risk_history(client, test_user_data, db_session):
    """测试风险评估历史"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = login_resp.json()["data"]["user"]["id"]

    # 直接插入风险记录
    from app.models.risk_assessment import RiskAssessment
    import uuid
    record = RiskAssessment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        risk_type="ascvd",
        risk_level="moderate",
        risk_score=5.0,
        risk_probability=12.5,
        assessed_at=datetime.now(timezone.utc),
    )
    db_session.add(record)
    await db_session.commit()

    resp = await client.get("/api/v1/dashboard/risk-assessment/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert data[0]["risk_type"] == "ascvd"
