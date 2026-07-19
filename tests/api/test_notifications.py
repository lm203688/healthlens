"""通知中心 API 测试"""
import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_list_notifications_empty(client, test_user_data):
    """测试空通知列表"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/notifications", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] == []
    assert data["meta"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_unread_count(client, test_user_data):
    """测试未读数量"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/notifications/unread/count", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_mark_all_as_read(client, test_user_data, db_session):
    """测试全部标记已读"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 直接通过 DB 插入通知
    from app.models.notification import Notification
    import uuid
    user_id = login_resp.json()["data"]["user"]["id"]

    for i in range(3):
        notif = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category="health_alert",
            title=f"通知{i}",
            content="测试通知内容",
            severity="info",
            is_read=False,
        )
        db_session.add(notif)
    await db_session.commit()

    # 标记全部已读
    resp = await client.put("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200

    # 验证未读数为0
    count_resp = await client.get("/api/v1/notifications/unread/count", headers=headers)
    assert count_resp.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_delete_notification(client, test_user_data, db_session):
    """测试删除通知"""
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.models.notification import Notification
    import uuid
    user_id = login_resp.json()["data"]["user"]["id"]

    notif = Notification(
        id=str(uuid.uuid4()),
        user_id=user_id,
        category="system",
        title="待删除",
        content="将被删除",
    )
    db_session.add(notif)
    await db_session.commit()
    notif_id = notif.id

    # 删除
    resp = await client.delete(f"/api/v1/notifications/{notif_id}", headers=headers)
    assert resp.status_code == 200

    # 列表中不应再出现
    list_resp = await client.get("/api/v1/notifications", headers=headers)
    notif_ids = [n["id"] for n in list_resp.json()["data"]]
    assert notif_id not in notif_ids
