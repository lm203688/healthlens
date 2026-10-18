"""Prescription CRUD + 403 权限测试"""
import uuid
import pytest


async def _create_doctor_token(db_session):
    """在 DB 中直接创建 doctor 用户，返回 access_token"""
    from app.models.user import User
    from app.utils.security import hash_password, create_access_token

    doctor_id = str(uuid.uuid4())
    doctor = User(
        id=doctor_id,
        email=f"doctor_{uuid.uuid4().hex[:8]}@healthlens.com",
        password_hash=hash_password("DoctorPass123!"),
        role="doctor",
    )
    db_session.add(doctor)
    await db_session.commit()

    token = create_access_token({"sub": doctor_id})
    return token, doctor_id


async def _create_patient_token(db_session):
    """在 DB 中直接创建 patient 用户，返回 access_token"""
    from app.models.user import User
    from app.utils.security import hash_password, create_access_token

    patient_id = str(uuid.uuid4())
    patient = User(
        id=patient_id,
        email=f"patient_{uuid.uuid4().hex[:8]}@healthlens.com",
        password_hash=hash_password("PatientPass123!"),
        role="patient",
    )
    db_session.add(patient)
    await db_session.commit()

    token = create_access_token({"sub": patient_id})
    return token, patient_id


@pytest.mark.asyncio
async def test_create_prescription_as_patient_403(client, db_session):
    """patient 角色创建处方应返回 403"""
    token, patient_id = await _create_patient_token(db_session)

    response = await client.post(
        "/api/v1/medications/prescriptions",
        json={
            "medications": [
                {
                    "drug_name": "阿莫西林",
                    "dosage": "500",
                    "dosage_unit": "mg",
                    "frequency": "tid",
                    "route": "口服",
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_prescribe_endpoint(client, db_session):
    """正常创建处方（doctor 用户）"""
    token, doctor_id = await _create_doctor_token(db_session)

    response = await client.post(
        "/api/v1/medications/prescriptions",
        json={
            "medications": [
                {
                    "drug_name": "阿托伐他汀",
                    "drug_code": "C10AA05",
                    "dosage": "20",
                    "dosage_unit": "mg",
                    "frequency": "qd",
                    "route": "口服",
                }
            ],
            "notes": "睡前服用",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["prescription_no"] is not None
    assert len(data["medications"]) == 1


@pytest.mark.asyncio
async def test_list_prescriptions(client, db_session):
    """查看处方列表"""
    token, doctor_id = await _create_doctor_token(db_session)

    # 先创建一个处方
    await client.post(
        "/api/v1/medications/prescriptions",
        json={
            "medications": [
                {"drug_name": "二甲双胍", "dosage": "500", "dosage_unit": "mg", "frequency": "bid", "route": "口服"}
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.get(
        "/api/v1/medications/prescriptions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_prescription_detail(client, db_session):
    """获取处方详情"""
    token, doctor_id = await _create_doctor_token(db_session)

    # 先创建
    create_resp = await client.post(
        "/api/v1/medications/prescriptions",
        json={
            "medications": [
                {"drug_name": "阿司匹林", "dosage": "100", "dosage_unit": "mg", "frequency": "qd", "route": "口服"}
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    prescription_id = create_resp.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/medications/prescriptions/{prescription_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == prescription_id
    assert data["medications"][0]["drug_name"] == "阿司匹林"


@pytest.mark.asyncio
async def test_update_prescription_status(client, db_session):
    """更新处方状态"""
    token, doctor_id = await _create_doctor_token(db_session)

    # 先创建
    create_resp = await client.post(
        "/api/v1/medications/prescriptions",
        json={
            "medications": [
                {"drug_name": "头孢克洛", "dosage": "250", "dosage_unit": "mg", "frequency": "tid", "route": "口服"}
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    prescription_id = create_resp.json()["data"]["id"]

    # activate
    response = await client.put(
        f"/api/v1/medications/prescriptions/{prescription_id}",
        json={"status": "activate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"

    # discontinue
    response = await client.put(
        f"/api/v1/medications/prescriptions/{prescription_id}",
        json={"status": "discontinue"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "discontinued"


@pytest.mark.asyncio
async def test_get_prescription_not_found(client, db_session):
    """不存在的处方返回 404"""
    token, doctor_id = await _create_doctor_token(db_session)

    response = await client.get(
        f"/api/v1/medications/prescriptions/{str(uuid.uuid4())}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
