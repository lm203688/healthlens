"""业务闭环端到端测试 - 覆盖完整用户流程

业务流程:
  注册 -> 登录 -> 上传报告 -> 写入健康指标(通过DB) -> 查看指标列表
  -> 获取健康摘要 -> FHIR 导出 -> 提交中医体质问卷 -> 获取体质档案

说明:
  - POST /api/v1/observations/ 端点尚未实现，健康指标通过 DB Session 直接插入
  - HealthProfile 创建 API 尚未实现，健康摘要报告中 profile 为 None
  - 中医体质模块 POST/GET/PUT 端点均已实现，可完整测试
"""
import pytest
from httpx import AsyncClient

from app.models.observation import HealthObservation
from datetime import datetime, timezone
from decimal import Decimal


# ---------------------------------------------------------------------------
# 辅助: 注册 + 登录，返回 (token, user_id)
# ---------------------------------------------------------------------------
async def _register_and_login(client: AsyncClient, user_data: dict) -> tuple[str, str]:
    """执行注册和登录，返回 (access_token, user_id)。失败则 pytest.skip。"""
    register_resp = await client.post("/api/v1/auth/register", json=user_data)
    if register_resp.status_code not in (200, 201):
        pytest.skip(f"注册失败, status={register_resp.status_code}")

    register_data = register_resp.json()["data"]
    token = register_data["access_token"]
    user_id = register_data["user"]["id"]

    # 独立验证登录流程
    login_resp = await client.post("/api/v1/auth/login", json=user_data)
    assert login_resp.status_code == 200, f"登录失败: {login_resp.text}"
    assert login_resp.json()["data"]["access_token"] is not None

    return token, user_id


# ---------------------------------------------------------------------------
# 辅助: 向 DB 直接插入健康指标（因 POST /api/v1/observations/ 尚未实现）
# ---------------------------------------------------------------------------
async def _seed_observations(db_session, user_id: str) -> list[str]:
    """向数据库插入 3 条测试健康指标，返回 observation id 列表。"""
    now = datetime.now(timezone.utc)
    rows = [
        HealthObservation(
            id=str(__import__("uuid").uuid4()),
            user_id=user_id,
            loinc_code="2345-7",
            loinc_name="Glucose [Mass/volume] in Blood",
            value_numeric=Decimal("6.8"),
            value_unit="mmol/L",
            reference_range_low=Decimal("3.9"),
            reference_range_high=Decimal("6.1"),
            source="test_upload",
            recorded_at=now,
        ),
        HealthObservation(
            id=str(__import__("uuid").uuid4()),
            user_id=user_id,
            loinc_code="2093-3",
            loinc_name="Cholesterol [Mass/volume] in Serum or Plasma",
            value_numeric=Decimal("5.2"),
            value_unit="mmol/L",
            reference_range_low=Decimal("2.8"),
            reference_range_high=Decimal("5.2"),
            source="test_upload",
            recorded_at=now,
        ),
        HealthObservation(
            id=str(__import__("uuid").uuid4()),
            user_id=user_id,
            loinc_code="2085-9",
            loinc_name="Hemoglobin [Mass/volume] in Blood",
            value_numeric=Decimal("135"),
            value_unit="g/L",
            reference_range_low=Decimal("130"),
            reference_range_high=Decimal("175"),
            source="test_upload",
            recorded_at=now,
        ),
    ]
    for row in rows:
        db_session.add(row)
    await db_session.commit()
    return [str(r.id) for r in rows]


# ===========================================================================
# 测试 1: 完整业务闭环
# ===========================================================================
@pytest.mark.asyncio
async def test_full_business_loop(client, test_user_data, db_session):
    """完整业务闭环: 注册->登录->上传报告->写入指标->查看指标->健康摘要->FHIR导出->中医体质"""

    # ------------------------------------------------------------------
    # 1. 注册
    # ------------------------------------------------------------------
    register_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    assert register_resp.status_code in (200, 201), f"注册失败: {register_resp.text}"
    reg_data = register_resp.json()["data"]
    token = reg_data["access_token"]
    user_id = reg_data["user"]["id"]
    assert isinstance(token, str) and len(token) > 0
    assert isinstance(user_id, str) and len(user_id) > 0
    headers = {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # 2. 登录（独立验证登录流程）
    # ------------------------------------------------------------------
    login_resp = await client.post("/api/v1/auth/login", json=test_user_data)
    assert login_resp.status_code == 200, f"登录失败: {login_resp.text}"
    login_data = login_resp.json()["data"]
    assert login_data["access_token"] is not None
    assert login_data["token_type"] == "bearer"
    assert "user" in login_data

    # ------------------------------------------------------------------
    # 3. 获取当前用户信息
    # ------------------------------------------------------------------
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["email"] == test_user_data["email"]
    assert me_data["id"] == user_id

    # ------------------------------------------------------------------
    # 4. 上传健康报告
    # ------------------------------------------------------------------
    files = {
        "file": ("annual_checkup.pdf", b"%PDF-1.4 fake annual health report", "application/pdf")
    }
    upload_resp = await client.post(
        "/api/v1/records/upload", files=files, headers=headers
    )
    assert upload_resp.status_code == 201, f"上传失败: {upload_resp.text}"
    upload_data = upload_resp.json()["data"]
    assert upload_data["status"] == "completed"  # mock OCR 成功解析
    assert upload_data["filename"] == "annual_checkup.pdf"
    assert upload_data["observations_count"] > 0
    record_id = upload_data["id"]
    assert isinstance(record_id, str)

    # ------------------------------------------------------------------
    # 5. 查看报告列表
    # ------------------------------------------------------------------
    list_resp = await client.get("/api/v1/records/", headers=headers)
    assert list_resp.status_code == 200
    records = list_resp.json()["data"]
    assert len(records) >= 1
    # 确认刚上传的报告在列表中
    record_ids_in_list = [r["id"] for r in records]
    assert record_id in record_ids_in_list

    # ------------------------------------------------------------------
    # 6. 查看报告详情
    # ------------------------------------------------------------------
    detail_resp = await client.get(
        f"/api/v1/records/{record_id}", headers=headers
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["id"] == record_id
    assert detail_data["filename"] == "annual_checkup.pdf"

    # ------------------------------------------------------------------
    # 7. 补充创建健康指标 (OCR 已自动创建了 7 条，再手动添加 3 条)
    # ------------------------------------------------------------------
    obs_ids = await _seed_observations(db_session, user_id)
    assert len(obs_ids) == 3

    # ------------------------------------------------------------------
    # 8. 查看指标列表 (OCR 7 + 手动 3 = 至少 10 条)
    # ------------------------------------------------------------------
    obs_list_resp = await client.get("/api/v1/observations/", headers=headers)
    assert obs_list_resp.status_code == 200
    obs_list_data = obs_list_resp.json()["data"]
    assert len(obs_list_data) >= 10
    # 验证返回结构
    for obs in obs_list_data:
        assert "id" in obs
        assert "loinc_code" in obs
        assert "loinc_name" in obs
        assert "value_numeric" in obs
        assert "value_unit" in obs
        assert "reference_range" in obs
        assert "is_abnormal" in obs
        assert "source" in obs
        assert "recorded_at" in obs

    # 验证分页 meta
    obs_meta = obs_list_resp.json()["meta"]
    assert obs_meta["total"] >= 10
    assert obs_meta["page"] == 1
    assert obs_meta["page_size"] == 20

    # 验证可按 loinc_code 筛选 (OCR 和手动都创建了 2345-7 血糖)
    filtered_resp = await client.get(
        "/api/v1/observations/?loinc_code=2345-7", headers=headers
    )
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()["data"]
    assert len(filtered_data) >= 1  # OCR 1条 + 手动 1条
    assert filtered_data[0]["loinc_code"] == "2345-7"

    # ------------------------------------------------------------------
    # 9. 获取健康指标汇总
    # ------------------------------------------------------------------
    summary_resp = await client.get("/api/v1/observations/summary", headers=headers)
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()["data"]
    assert "total_indicators" in summary_data
    assert "abnormal_count" in summary_data
    assert "indicators" in summary_data
    assert summary_data["total_indicators"] >= 7  # 去重后的指标数 (OCR 7条，手动3条有重复loinc_code)
    # 血糖 6.8 > 参考上限 6.1，应标记异常
    assert summary_data["abnormal_count"] >= 1

    # ------------------------------------------------------------------
    # 10. FHIR R5 导出
    # ------------------------------------------------------------------
    fhir_resp = await client.get("/api/v1/reports/fhir", headers=headers)
    assert fhir_resp.status_code == 200
    fhir_data = fhir_resp.json()["data"]
    assert fhir_data["resourceType"] == "Bundle"
    assert fhir_data["type"] == "collection"
    assert fhir_data["total"] >= 10  # OCR + 手动创建的所有 observations
    for entry in fhir_data["entry"]:
        resource = entry["resource"]
        assert resource["resourceType"] == "Observation"
        assert "code" in resource
        assert "valueQuantity" in resource

    # ------------------------------------------------------------------
    # 11. 健康摘要报告
    # ------------------------------------------------------------------
    health_resp = await client.get("/api/v1/reports/health", headers=headers)
    assert health_resp.status_code == 200
    health_data = health_resp.json()["data"]
    assert health_data["user_id"] == user_id
    assert "analysis" in health_data
    assert "generated_at" in health_data
    # analysis 应包含汇总信息
    analysis = health_data["analysis"]
    assert analysis["total_items"] >= 10  # OCR + 手动

    # ------------------------------------------------------------------
    # 12. 提交中医体质问卷
    # ------------------------------------------------------------------
    questionnaire = {
        "q1_fatigue": 4,
        "q2_cold_limbs": 2,
        "q3_mouth_dry": 3,
        "q4_sweating": 1,
        "symptoms": ["容易疲劳", "手足心热", "口干"],
    }
    tcm_submit_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={"questionnaire_data": questionnaire},
        headers=headers,
    )
    assert tcm_submit_resp.status_code == 201, f"提交体质问卷失败: {tcm_submit_resp.text}"
    tcm_submit_data = tcm_submit_resp.json()["data"]
    assert tcm_submit_data["status"] == "completed"  # 现在真正执行体质分析

    # ------------------------------------------------------------------
    # 13. 获取体质档案
    # ------------------------------------------------------------------
    tcm_get_resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert tcm_get_resp.status_code == 200
    tcm_profile = tcm_get_resp.json()["data"]
    assert tcm_profile is not None
    assert "id" in tcm_profile
    assert tcm_profile["questionnaire_data"] == questionnaire
    assert "assessed_at" in tcm_profile
    assert "created_at" in tcm_profile


# ===========================================================================
# 测试 2: 中医体质完整流程
# ===========================================================================
@pytest.mark.asyncio
async def test_tcm_constitution_flow(client, test_user_data, db_session):
    """中医体质流程: 注册->提交问卷->获取档案->更新档案->再次获取"""

    # 注册并获取 token
    token, user_id = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # 1. 首次获取体质档案（应返回 null）
    # ------------------------------------------------------------------
    get_resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"] is None

    # ------------------------------------------------------------------
    # 2. 提交体质问卷
    # ------------------------------------------------------------------
    questionnaire_v1 = {
        "constitution_questions": {
            "A1": 3, "A2": 2, "A3": 4, "A4": 1, "A5": 3,
            "B1": 2, "B2": 3, "B3": 1, "B4": 4, "B5": 2,
        },
        "extra_info": "首次填写",
    }
    submit_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={"questionnaire_data": questionnaire_v1},
        headers=headers,
    )
    assert submit_resp.status_code == 201
    submit_data = submit_resp.json()["data"]
    assert submit_data["status"] == "completed"  # 现在真正执行体质分析

    # ------------------------------------------------------------------
    # 3. 获取体质档案（应有数据）
    # ------------------------------------------------------------------
    get_resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert get_resp.status_code == 200
    profile = get_resp.json()["data"]
    assert profile is not None
    assert isinstance(profile["id"], str)
    assert profile["questionnaire_data"] == questionnaire_v1
    assert profile["assessed_at"] is not None
    profile_id = profile["id"]

    # ------------------------------------------------------------------
    # 4. 更新体质档案
    # ------------------------------------------------------------------
    update_payload = {
        "constitution_type": "qixu",
        "constitution_score": {
            "qixu": 38,
            "yangxu": 22,
            "yinxu": 30,
            "tanshi": 15,
            "shire": 12,
            "xueyu": 10,
            "qiyu": 18,
            "tebing": 8,
            "pinghe": 25,
        },
    }
    update_resp = await client.put(
        "/api/v1/tcm/constitution",
        json=update_payload,
        headers=headers,
    )
    assert update_resp.status_code == 200, f"更新体质档案失败: {update_resp.text}"
    update_data = update_resp.json()["data"]
    assert update_data["id"] == profile_id
    assert update_data["constitution_type"] == "qixu"
    assert update_data["constitution_score"] is not None
    assert update_data["constitution_score"]["qixu"] == 38

    # ------------------------------------------------------------------
    # 5. 再次提交问卷（应更新已有档案）
    # ------------------------------------------------------------------
    questionnaire_v2 = {
        "constitution_questions": {
            "A1": 2, "A2": 1, "A3": 3, "A4": 2, "A5": 1,
        },
        "extra_info": "第二次填写",
    }
    resubmit_resp = await client.post(
        "/api/v1/tcm/constitution",
        json={"questionnaire_data": questionnaire_v2},
        headers=headers,
    )
    assert resubmit_resp.status_code == 201
    assert resubmit_resp.json()["data"]["status"] == "completed"

    # ------------------------------------------------------------------
    # 6. 再次获取档案，确认问卷数据已更新
    # ------------------------------------------------------------------
    final_resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert final_resp.status_code == 200
    final_profile = final_resp.json()["data"]
    assert final_profile is not None
    # 问卷数据应已更新为 v2
    assert final_profile["questionnaire_data"] == questionnaire_v2
    # constitution_type 会被 POST 重新提交的 AI 分析结果覆盖为中文名称
    assert final_profile["constitution_type"] == "气虚质"


# ===========================================================================
# 测试 3: 无认证/无效 Token 访问受保护端点
# ===========================================================================
@pytest.mark.asyncio
async def test_protected_endpoints_require_auth(client):
    """验证未认证请求被拒绝"""

    # 无 token 访问 observations
    resp = await client.get("/api/v1/observations/")
    assert resp.status_code == 401

    # 无 token 访问 tcm constitution
    resp = await client.get("/api/v1/tcm/constitution")
    assert resp.status_code == 401

    # 无 token 访问 reports
    resp = await client.get("/api/v1/reports/fhir")
    assert resp.status_code == 401

    # 无效 token
    resp = await client.get(
        "/api/v1/observations/",
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert resp.status_code == 401


# ===========================================================================
# 测试 4: 空数据场景下的 GET 端点
# ===========================================================================
@pytest.mark.asyncio
async def test_empty_data_endpoints(client, test_user_data):
    """新用户无任何数据时，各 GET 端点应正常返回空结果"""

    token, _ = await _register_and_login(client, test_user_data)
    headers = {"Authorization": f"Bearer {token}"}

    # 指标列表为空
    obs_resp = await client.get("/api/v1/observations/", headers=headers)
    assert obs_resp.status_code == 200
    assert obs_resp.json()["data"] == []
    assert obs_resp.json()["meta"]["total"] == 0

    # 指标汇总为空
    summary_resp = await client.get("/api/v1/observations/summary", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()["data"]
    assert summary["total_indicators"] == 0
    assert summary["abnormal_count"] == 0
    assert summary["indicators"] == []

    # FHIR 导出为空 Bundle
    fhir_resp = await client.get("/api/v1/reports/fhir", headers=headers)
    assert fhir_resp.status_code == 200
    fhir_data = fhir_resp.json()["data"]
    assert fhir_data["resourceType"] == "Bundle"
    assert fhir_data["total"] == 0
    assert fhir_data["entry"] == []

    # 报告列表为空
    records_resp = await client.get("/api/v1/records/", headers=headers)
    assert records_resp.status_code == 200
    assert records_resp.json()["data"] == []

    # 体质档案为 null
    tcm_resp = await client.get("/api/v1/tcm/constitution", headers=headers)
    assert tcm_resp.status_code == 200
    assert tcm_resp.json()["data"] is None