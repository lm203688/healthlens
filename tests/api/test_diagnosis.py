"""西医诊断 + 处方系统端到端测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_diagnosis_with_abnormal_observations(client, test_user_data):
    """测试: 上传报告产生异常指标 → 触发AI诊断 → 查看诊断结果 → 开具处方"""
    # 注册登录
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 上传报告 (OCR会产生异常指标，如血糖6.8>6.1)
    files = {"file": ("test_report.pdf", b"%PDF-1.4 fake content", "application/pdf")}
    upload_resp = await client.post("/api/v1/records/upload", files=files, headers=headers)
    assert upload_resp.status_code == 201

    # 触发诊断 (实际端点返回 202, 需要 AnalyzeRequest body)
    diag_resp = await client.post(
        "/api/v1/diagnosis/analyze",
        json={"include_observations": True},
        headers=headers,
    )
    assert diag_resp.status_code == 202
    diag_data = diag_resp.json()["data"]
    assert diag_data["status"] == "completed"
    assert diag_data["total_findings"] > 0
    # 应检测到血糖偏高
    finding_names = [f["name"] for f in diag_data["findings"]]
    assert any("血糖" in n for n in finding_names)

    # 获取诊断列表 (实际端点: /diagnosis/results)
    list_resp = await client.get("/api/v1/diagnosis/results", headers=headers)
    assert list_resp.status_code == 200
    diag_list = list_resp.json()["data"]
    assert len(diag_list) > 0

    # 查看诊断详情 (实际端点: /diagnosis/results/{id})
    diag_id = diag_list[0]["id"]
    detail_resp = await client.get(f"/api/v1/diagnosis/results/{diag_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["icd_code"] is not None


@pytest.mark.asyncio
async def test_prescribe_medication(client, test_user_data, db_session):
    """测试: 诊断后开具处方"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = register_resp.json()["data"]["user"]["id"]

    # 升级为 doctor (/prescribe 需要 doctor 权限)
    from sqlalchemy import select
    from app.models.user import User
    result = await db_session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.role = "doctor"
        await db_session.commit()

    # 上传报告并诊断
    files = {"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")}
    await client.post("/api/v1/records/upload", files=files, headers=headers)
    diag_resp = await client.post(
        "/api/v1/diagnosis/analyze",
        json={"include_observations": True},
        headers=headers,
    )
    assert diag_resp.status_code == 202

    # 获取第一个诊断ID
    list_resp = await client.get("/api/v1/diagnosis/results", headers=headers)
    diag_list = list_resp.json()["data"]
    if not diag_list:
        pytest.skip("No diagnosis generated")
    diag_id = diag_list[0]["id"]

    # 开具处方 (实际端点: /medications/prescribe, body 传 diagnosis_id)
    rx_resp = await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diag_id},
        headers=headers,
    )
    assert rx_resp.status_code == 201
    rx_data = rx_resp.json()["data"]
    assert rx_data["drug_name"] is not None
    assert rx_data["dosage"] is not None

    # 查看处方历史
    history_resp = await client.get("/api/v1/medications/history", headers=headers)
    assert history_resp.status_code == 200
    history_data = history_resp.json()["data"]
    assert len(history_data) > 0


@pytest.mark.asyncio
async def test_diagnosis_no_data(client, test_user_data):
    """测试: 无数据时触发诊断"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 新用户无数据，诊断应返回 no_data
    diag_resp = await client.post(
        "/api/v1/diagnosis/analyze",
        json={"include_observations": True},
        headers=headers,
    )
    assert diag_resp.status_code == 202
    assert diag_resp.json()["data"]["status"] == "no_data"