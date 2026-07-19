import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_upload_record(client, test_user_data):
    """测试报告上传"""
    # 先注册登录获取 token
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code in (200, 201):
        login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
        if login_resp.status_code == 200:
            token = login_resp.json()["data"]["access_token"]
        else:
            pytest.skip("Login failed")
    else:
        pytest.skip("Registration failed")

    # 上传一个测试文件
    files = {"file": ("test_report.pdf", b"%PDF-1.4 fake content", "application/pdf")}
    response = await client.post(
        "/api/v1/records/upload",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "completed"  # mock OCR 成功解析
    assert data["filename"] == "test_report.pdf"
    assert data["observations_count"] > 0  # OCR 提取了指标
    record_id = data["id"]

    # 获取记录列表
    list_resp = await client.get(
        "/api/v1/records/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) > 0

    # 获取记录详情
    detail_resp = await client.get(
        f"/api/v1/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["id"] == record_id


@pytest.mark.asyncio
async def test_delete_record(client, test_user_data):
    """上传后删除"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    if login_resp.status_code != 200:
        pytest.skip("Login failed")
    token = login_resp.json()["data"]["access_token"]

    files = {"file": ("to_delete.pdf", b"%PDF-1.4 fake content", "application/pdf")}
    upload_resp = await client.post(
        "/api/v1/records/upload",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_resp.status_code == 201
    record_id = upload_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_resp.status_code == 200

    # 再次查询应返回 404
    get_resp = await client.get(
        f"/api/v1/records/{record_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_reprocess_record(client, test_user_data):
    """上传后重新解析"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    if login_resp.status_code != 200:
        pytest.skip("Login failed")
    token = login_resp.json()["data"]["access_token"]

    files = {"file": ("reprocess.pdf", b"%PDF-1.4 fake content", "application/pdf")}
    upload_resp = await client.post(
        "/api/v1/records/upload",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_resp.status_code == 201
    record_id = upload_resp.json()["data"]["id"]

    reprocess_resp = await client.post(
        f"/api/v1/records/{record_id}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reprocess_resp.status_code == 200
    data = reprocess_resp.json()["data"]
    assert data["status"] == "reprocessing"
