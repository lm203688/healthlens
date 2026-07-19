"""中医辨证 → 方剂推荐 → 配送订单 端到端测试"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tcm_full_diagnosis_flow(client, test_user_data):
    """完整中医流程: 提交问卷→触发辨证→方剂推荐→创建订单"""
    # 注册登录
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    token = login_resp.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 提交体质问卷 (气虚质倾向)
    constitution_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={
            "questionnaire_data": {
                "answers": {
                    "dim_qixu": [4, 4, 3, 4, 3],  # 气虚高分
                    "dim_pinghe": [2, 2, 3, 2, 2],  # 平和低分
                    "dim_yangxu": [2, 1, 2, 1, 0],
                    "dim_yinxu": [1, 2, 1, 0, 0],
                    "dim_tanshi": [1, 1, 2, 0, 0],
                    "dim_shire": [1, 0, 1, 0, 0],
                    "dim_xueyu": [1, 0, 0, 0, 0],
                    "dim_qiyu": [1, 1, 0, 0, 0],
                    "dim_tebing": [0, 0, 0, 0, 0],
                }
            }
        },
        headers=headers,
    )
    assert constitution_resp.status_code == 201
    assert constitution_resp.json()["data"]["status"] == "completed"
    assert constitution_resp.json()["data"]["primary_type"] == "qixu"

    # 2. 触发 AI 辨证
    diagnose_resp = await client.post("/api/v1/tcm/diagnose", headers=headers)
    assert diagnose_resp.status_code == 202
    diag_data = diagnose_resp.json()["data"]
    assert diag_data["syndrome_name"] is not None
    assert diag_data["principle"] is not None
    syndrome_id = diag_data["id"]

    # 3. 方剂推荐
    formula_resp = await client.post(
        "/api/v1/tcm/formula/recommend",
        json={"syndrome_id": syndrome_id},
        headers=headers,
    )
    assert formula_resp.status_code == 201
    formula_data = formula_resp.json()["data"]
    assert formula_data["formula_name"] is not None
    assert formula_data["composition"] is not None
    recommendation_id = formula_data["recommendation_id"]

    # 4. 创建配送订单
    order_resp = await client.post(
        "/api/v1/tcm/order/create",
        json={
            "formula_id": recommendation_id,
            "delivery_address": "北京市朝阳区某某小区1号楼101",
        },
        headers=headers,
    )
    assert order_resp.status_code == 201
    order_data = order_resp.json()["data"]
    assert order_data["order_id"] is not None
    assert order_data["pharmacy_name"] is not None

    # 5. 查看订单详情
    orders_resp = await client.get("/api/v1/tcm/orders", headers=headers)
    assert orders_resp.status_code == 200
    assert len(orders_resp.json()["data"]) > 0

    # 6. 取消订单
    order_id = order_data["order_id"]
    cancel_resp = await client.put(f"/api/v1/tcm/order/{order_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["order_status"] == "cancelled"