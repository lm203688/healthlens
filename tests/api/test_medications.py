"""西药 API 测试"""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone

from app.models.observation import HealthObservation
from app.models.diagnosis import DiagnosisResult
from app.models.user import User


async def _register_and_login(client, user_data):
    """注册并登录，返回 (token, user_id)"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    return token, user_id


async def _upgrade_to_doctor(db_session, user_id):
    """将用户升级为 doctor 角色（/prescribe 需要 doctor 权限）"""
    from sqlalchemy import select
    result = await db_session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.role = "doctor"
        await db_session.commit()


async def _create_diagnosis(db_session, user_id, icd_code="5A11"):
    """在数据库中直接创建诊断记录，返回 diagnosis_id"""
    diagnosis = DiagnosisResult(
        id=str(uuid.uuid4()),
        user_id=user_id,
        diagnosis_text="糖尿病",
        icd_code=icd_code,
        confidence=Decimal("0.85"),
        severity="moderate",
        is_ai_generated=True,
        status="pending",
    )
    db_session.add(diagnosis)
    await db_session.commit()
    await db_session.refresh(diagnosis)
    return str(diagnosis.id)


@pytest.mark.asyncio
async def test_get_recommendations(client, test_user_data, db_session):
    """需要 diagnosis_id，先创建诊断再查询推荐"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 升级为 doctor 以便调用 /prescribe
    await _upgrade_to_doctor(db_session, user_id)

    # 创建诊断记录
    diagnosis_id = await _create_diagnosis(db_session, user_id, icd_code="5A11")

    # 先通过 prescribe 创建一条推荐记录
    prescribe_resp = await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diagnosis_id},
        headers=headers,
    )
    assert prescribe_resp.status_code == 201, f"生成处方失败: {prescribe_resp.text}"

    # 查询推荐
    rec_resp = await client.get(
        "/api/v1/medications/recommend",
        params={"diagnosis_id": diagnosis_id},
        headers=headers,
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["success"] is True
    assert rec_data["meta"]["diagnosis_id"] == diagnosis_id
    assert rec_data["meta"]["count"] >= 1
    assert rec_data["data"][0]["drug_name"] == "二甲双胍"


@pytest.mark.asyncio
async def test_prescribe(client, test_user_data, db_session):
    """创建诊断后调用 /medications/prescribe 生成处方"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 升级为 doctor
    await _upgrade_to_doctor(db_session, user_id)

    # 创建诊断记录（ICD 5C70 = 高脂血症 -> 阿托伐他汀）
    diagnosis_id = await _create_diagnosis(db_session, user_id, icd_code="5C70")

    resp = await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diagnosis_id},
        headers=headers,
    )

    assert resp.status_code == 201, f"生成处方失败: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["diagnosis_id"] == diagnosis_id
    assert data["data"]["drug_name"] == "阿托伐他汀"
    assert data["data"]["drug_code"] == "C10AA05"
    assert data["data"]["dosage"] == "20"
    assert data["data"]["frequency"] == "qd"


@pytest.mark.asyncio
async def test_prescribe_forbidden_for_patient(client, test_user_data, db_session):
    """patient 角色调用 /prescribe 应返回 403"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    diagnosis_id = await _create_diagnosis(db_session, user_id)

    resp = await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diagnosis_id},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_medication_history(client, test_user_data, db_session):
    """查看用药历史"""
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 升级为 doctor
    await _upgrade_to_doctor(db_session, user_id)

    # 创建两个诊断并各生成一个处方
    diag_id_1 = await _create_diagnosis(db_session, user_id, icd_code="5A11")
    diag_id_2 = await _create_diagnosis(db_session, user_id, icd_code="5C70")

    await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diag_id_1},
        headers=headers,
    )
    await client.post(
        "/api/v1/medications/prescribe",
        json={"diagnosis_id": diag_id_2},
        headers=headers,
    )

    # 查看用药历史
    history_resp = await client.get(
        "/api/v1/medications/history", headers=headers
    )
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["success"] is True
    assert history_data["meta"]["total"] == 2
    assert history_data["meta"]["page"] == 1

    drug_names = [item["drug_name"] for item in history_data["data"]]
    assert "二甲双胍" in drug_names
    assert "阿托伐他汀" in drug_names
