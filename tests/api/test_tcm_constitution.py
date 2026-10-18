"""TCM 体质 API 测试"""
import pytest


async def _register_and_login(client, user_data):
    """注册并登录，返回 (token, user_id)"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    return token, user_id


@pytest.mark.asyncio
async def test_submit_constitution(client, test_user_data):
    """提交体质问卷"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/tcm/constitution",
        json={
            "questionnaire_data": {
                "answers": {
                    "dim_qixu": [4, 4, 3, 4, 3],
                    "dim_pinghe": [2, 2, 3, 2, 2],
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
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"] is not None


@pytest.mark.asyncio
async def test_get_constitution_empty(client, test_user_data):
    """未提交时获取体质为空"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"] is None
    assert data["meta"]["message"] == "No constitution profile found"


@pytest.mark.asyncio
async def test_update_constitution_type(client, test_user_data):
    """更新体质类型"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 先提交问卷创建档案
    submit_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={
            "questionnaire_data": {
                "answers": {
                    "dim_qixu": [4, 4, 3, 4, 3],
                    "dim_pinghe": [2, 2, 3, 2, 2],
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
    assert submit_resp.status_code == 201

    # 更新体质类型
    update_resp = await client.put(
        "/api/v1/tcm/constitution",
        json={"constitution_type": "yangxu"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["success"] is True
    assert data["data"]["constitution_type"] == "yangxu"


@pytest.mark.asyncio
async def test_update_constitution_invalid_type(client, test_user_data):
    """非法体质类型应返回 422"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 先提交问卷创建档案
    submit_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={
            "questionnaire_data": {
                "answers": {
                    "dim_qixu": [4, 4, 3, 4, 3],
                    "dim_pinghe": [2, 2, 3, 2, 2],
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
    assert submit_resp.status_code == 201

    # 使用非法类型更新
    update_resp = await client.put(
        "/api/v1/tcm/constitution",
        json={"constitution_type": "invalid_type"},
        headers=headers,
    )
    assert update_resp.status_code == 422
