"""TCM 配送订单 API 测试"""
import pytest
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.models.tcm_formula import (
    TcmDeliveryOrder,
    TcmFormulaRecommendation,
)
from app.models.tcm_syndrome import TcmSyndromeDiagnosis
from app.models.tcm_profile import TcmProfile


async def _register_and_login(client, user_data):
    """注册并登录，返回 (token, user_id)"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    return token, user_id


async def _create_order(db_session, user_id, order_status="pending"):
    """在数据库中直接创建配送订单，返回 order_id"""
    order_id = str(uuid.uuid4())
    formula_id = str(uuid.uuid4())
    syndrome_id = str(uuid.uuid4())

    # 创建辨证记录（FK 需要存在）
    syndrome = TcmSyndromeDiagnosis(
        id=syndrome_id,
        user_id=user_id,
        syndrome_code="BNP010",
        syndrome_name="气血两虚证",
        confidence=Decimal("0.8"),
        status="pending",
    )
    db_session.add(syndrome)

    # 创建方剂推荐（FK 需要存在）
    formula = TcmFormulaRecommendation(
        id=formula_id,
        syndrome_id=syndrome_id,
        formula_name="四君子汤",
        formula_source="《太平惠民和剂局方》",
        original_composition={"人参": "9g", "白术": "9g", "茯苓": "9g", "甘草": "6g"},
    )
    db_session.add(formula)

    order = TcmDeliveryOrder(
        id=order_id,
        user_id=user_id,
        formula_id=formula_id,
        pharmacy_name="测试药房",
        order_status=order_status,
        delivery_address="北京市朝阳区某某小区1号楼101",
        total_fee=Decimal("128.50"),
        ordered_at=datetime.now(timezone.utc),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return str(order.id)


@pytest.mark.asyncio
async def test_create_order(client, test_user_data, db_session):
    """创建配送订单 - 通过 db 直接插入数据后用 API 查询验证"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    order_id = await _create_order(db_session, user_id, order_status="pending")

    # 通过 API 查询订单详情验证创建成功
    detail_resp = await client.get(
        f"/api/v1/tcm/order/{order_id}", headers=headers
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()["data"]
    assert data["id"] == order_id
    assert data["pharmacy_name"] == "测试药房"
    assert data["order_status"] == "pending"
    assert data["total_fee"] == 128.5
    assert data["delivery_address"] is not None


@pytest.mark.asyncio
async def test_list_orders(client, test_user_data, db_session):
    """查询订单列表"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 创建两个订单
    await _create_order(db_session, user_id, order_status="pending")
    await _create_order(db_session, user_id, order_status="shipped")

    # 查询列表
    list_resp = await client.get("/api/v1/tcm/orders", headers=headers)
    assert list_resp.status_code == 200
    resp_data = list_resp.json()
    assert resp_data["success"] is True
    assert resp_data["meta"]["total"] == 2
    assert len(resp_data["data"]) == 2

    # 按状态筛选
    filter_resp = await client.get(
        "/api/v1/tcm/orders", params={"status": "pending"}, headers=headers
    )
    assert filter_resp.status_code == 200
    filter_data = filter_resp.json()
    assert filter_data["meta"]["total"] == 1
    assert filter_data["data"][0]["order_status"] == "pending"


@pytest.mark.asyncio
async def test_cancel_order_pending(client, test_user_data, db_session):
    """pending 状态可取消"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    order_id = await _create_order(db_session, user_id, order_status="pending")

    cancel_resp = await client.put(
        f"/api/v1/tcm/order/{order_id}/cancel", headers=headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["order_status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_order_non_pending(client, test_user_data, db_session):
    """shipped 状态不可取消应返回 400"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    order_id = await _create_order(db_session, user_id, order_status="shipped")

    cancel_resp = await client.put(
        f"/api/v1/tcm/order/{order_id}/cancel", headers=headers
    )
    assert cancel_resp.status_code == 400
