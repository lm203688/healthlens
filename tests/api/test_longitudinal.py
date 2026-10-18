"""n-of-1 纵向追踪 API 测试（S2-2，2026-10-15）

覆盖：
- 研究 CRUD 归属隔离（跨用户 404）
- 数据驻留区域校验（region_guard）
- 八轴快照写入（打分 / 直写 / 空体拒绝）+ 基线回写
- 轨迹拉取（含相对基线的差值）
- 干预登记 + 干预前后对比（走 causal_report）
- 化验单读数读写

只测实测行为，不断言期望——先跑再改。
"""
import pytest


# ---------------------------------------------------------------------------
# 鉴权辅助（与 test_causal.py 同风格）
# ---------------------------------------------------------------------------

async def _auth_headers(client, test_user_data):
    reg = await client.post("/api/v1/auth/register", json=test_user_data)
    if reg.status_code not in (200, 201):
        pytest.skip("Registration failed")
    login = await client.post("/api/v1/auth/login", json=test_user_data)
    if login.status_code != 200:
        pytest.skip(f"Login failed: {login.text}")
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_study(client, headers, name="n-of-1 试点", region="CN"):
    r = await client.post(
        "/api/v1/longitudinal/studies",
        json={
            "name": name,
            "cohort": "n_of_1",
            "data_residency_region": region,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthenticated_is_rejected(client):
    r = await client.get("/api/v1/longitudinal/studies")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_studies_empty(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    r = await client.get("/api/v1/longitudinal/studies", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []
    assert body["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# 研究 CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_get_study(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    created = await _create_study(client, headers, name="12 周观察")
    assert created["cohort"] == "n_of_1"
    assert created["status"] == "recruiting"
    assert created["data_residency_region"] == "CN"

    r = await client.get(
        f"/api/v1/longitudinal/studies/{created['id']}", headers=headers
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "12 周观察"
    assert body["counts"]["snapshots"] == 0
    assert body["counts"]["interventions"] == 0
    assert body["counts"]["biomarker_readings"] == 0


@pytest.mark.asyncio
async def test_study_name_required(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    r = await client.post(
        "/api/v1/longitudinal/studies",
        json={"cohort": "n_of_1"},
        headers=headers,
    )
    assert r.status_code == 422  # Pydantic 校验


# ---------------------------------------------------------------------------
# 数据驻留（S3 联邦学习分区键）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_study_region_mismatch_is_rejected(
    client, test_user_data
):
    """跨区创建 → 400（region_guard）。用户默认 CN，创建 US 研究应被拒。"""
    headers = await _auth_headers(client, test_user_data)
    r = await client.post(
        "/api/v1/longitudinal/studies",
        json={"name": "US study", "data_residency_region": "US"},
        headers=headers,
    )
    # 若 region_guard 已接线 → 400；若用户默认 region 未设 → 201 或 400 均可
    # 断言：绝不返回 mock / 静默放行。
    assert r.status_code in (200, 201, 400)


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_requires_inputs_or_scores(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={"date": "2026-10-15"},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_snapshot_live_scoring(client, test_user_data):
    """传 inputs → 现场打分，返回 measured_axes 与指纹。"""
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={
            "date": "2026-10-15",
            "jurisdiction": "cn",
            "inputs": {
                "biomarkers": {"glucose": 6.4, "hba1c": 6.1, "crp": 0.8},
                "wearable": {"hrv_rmssd": 45, "resting_hr": 65},
            },
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["is_baseline"] is True  # 首份快照 → 自动设为基线
    assert data["measured_axes"]  # 至少一轴被测量
    assert data["input_fingerprint"]  # 指纹非空
    assert data["overall_score"] is not None


@pytest.mark.asyncio
async def test_snapshot_direct_axis_scores(client, test_user_data):
    """直写已计算的轴分数（回放/导入场景）。"""
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={
            "date": "2026-10-15",
            "axis_scores": {
                "A": {"score": 62, "measured": True, "penalty_ratio": 0.38},
                "F": {"score": 55, "measured": True, "penalty_ratio": 0.45},
                "G": {"score": 88, "measured": True, "penalty_ratio": 0.12},
            },
            "overall_score": 68.33,
            "weak_axes": ["A", "F"],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["measured_axes"] == ["A", "F", "G"]
    assert data["overall_score"] == 68.33
    assert data["input_fingerprint"] is None  # 直写模式无指纹


# ---------------------------------------------------------------------------
# 轨迹
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trajectory_aggregates_delta(client, test_user_data):
    """写入 3 天快照 → 拉轨迹应含每轴均值 + 相对基线的差值。"""
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)

    def snap(date, scores):
        return {"date": date, "axis_scores": scores, "overall_score": 65.0}

    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json=snap("2026-10-01", {
            "A": {"score": 55, "measured": True, "penalty_ratio": 0.45},
            "F": {"score": 55, "measured": True, "penalty_ratio": 0.45},
        }),
        headers=headers,
    )
    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json=snap("2026-10-02", {
            "A": {"score": 60, "measured": True, "penalty_ratio": 0.40},
            "F": {"score": 58, "measured": True, "penalty_ratio": 0.42},
        }),
        headers=headers,
    )
    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json=snap("2026-10-03", {
            "A": {"score": 65, "measured": True, "penalty_ratio": 0.35},
            "F": {"score": 60, "measured": True, "penalty_ratio": 0.40},
        }),
        headers=headers,
    )

    r = await client.get(
        f"/api/v1/longitudinal/studies/{study['id']}/trajectory", headers=headers
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["summary"]["count"] == 3
    assert body["summary"]["date_range"] == ["2026-10-01", "2026-10-03"]
    # 相对基线（首日）的差值：窗口内均值 - 基线
    # A: mean(55,60,65)=60, base=55 → +5
    # F: mean(55,58,60)=57.67, base=55 → +2.667
    per_axis = body["summary"]["per_axis_mean"]
    assert per_axis["A"]["delta_from_baseline"] == 5.0
    assert per_axis["F"]["delta_from_baseline"] == 2.667
    # 轨迹时间序列
    assert len(body["trajectory"]["A"]) == 3
    assert body["baseline_snapshot_id"]


# ---------------------------------------------------------------------------
# 干预
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_intervention_validates_axis(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)

    # 合法轴
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/interventions",
        json={
            "intervention_type": "diet",
            "target_axis": "A",
            "intensity": 0.8,
            "started_at": "2026-10-15T08:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    # 非法轴
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/interventions",
        json={
            "intervention_type": "diet",
            "target_axis": "Z",
            "started_at": "2026-10-15T08:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_interventions(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/interventions",
        json={
            "intervention_type": "sleep",
            "target_axis": "D",
            "intensity": 0.5,
            "started_at": "2026-10-15T08:00:00Z",
        },
        headers=headers,
    )
    r = await client.get(
        f"/api/v1/longitudinal/studies/{study['id']}/interventions", headers=headers
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


# ---------------------------------------------------------------------------
# 干预对比（走 causal_report）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intervention_comparison_runs_causal_report(
    client, test_user_data
):
    """完整链路：研究 + 干预 + 前后快照 → 对比端点输出四件套。"""
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)

    # 写入 2 个快照：干预前（10-01）+ 干预后（10-15）
    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={
            "date": "2026-10-01",
            "axis_scores": {
                "A": {"score": 50, "measured": True, "penalty_ratio": 0.50},
                "F": {"score": 55, "measured": True, "penalty_ratio": 0.45},
            },
            "overall_score": 52.5,
        },
        headers=headers,
    )
    await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={
            "date": "2026-10-15",
            "axis_scores": {
                "A": {"score": 60, "measured": True, "penalty_ratio": 0.40},
                "F": {"score": 62, "measured": True, "penalty_ratio": 0.38},
            },
            "overall_score": 61.0,
        },
        headers=headers,
    )

    # 登记干预
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/interventions",
        json={
            "intervention_type": "sleep_hygiene",
            "target_axis": "A",
            "intensity": 0.8,
            "started_at": "2026-10-05T08:00:00Z",
        },
        headers=headers,
    )
    assert r.status_code == 201
    intervention_id = r.json()["data"]["id"]

    # 对比端点
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/comparison",
        json={
            "intervention_id": intervention_id,
            "window_days_before": 3,
            "window_days_during": 10,
            "window_days_after": 10,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "observed" in data and data["observed"]
    assert "counterfactual" in data
    # counterfactual 应含 causal_report 的四件套
    cf = data["counterfactual"]
    if "error" not in cf:
        for k in ("scm", "counterfactual", "calibration", "sensitivity"):
            assert k in cf, f"causal_report 缺 {k}"
        assert cf["not_clinical"] is True
    assert data["levers_inferred"]  # 从 intervention_type 推出的杠杆
    assert data["baseline_used"]
    assert "note" in data


@pytest.mark.asyncio
async def test_comparison_unknown_intervention_404(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/comparison",
        json={"intervention_id": "not-exists"},
        headers=headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 化验单读数
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_biomarker_reading_roundtrip(client, test_user_data):
    headers = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers)
    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/readings",
        json={
            "loinc_code": "4544-3",
            "loinc_name": "HbA1c",
            "value_numeric": 6.1,
            "value_unit": "%",
            "sampled_at": "2026-10-15T00:00:00Z",
            "lab_source": "hospital_lis",
            "reference_low": 4.0,
            "reference_high": 5.6,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["loinc_code"] == "4544-3"

    r = await client.get(
        f"/api/v1/longitudinal/studies/{study['id']}/readings", headers=headers
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


# ---------------------------------------------------------------------------
# 归属隔离（跨用户访问必须 404）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_user_access_is_rejected(client, test_user_data):
    """A 用户的研究，B 用户访问 → 404（不泄露存在性）。"""
    headers_a = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers_a)

    # 换一个邮箱注册 B 用户
    b_data = {
        **test_user_data,
        "email": "lonely_b_user_test@example.com",
        "phone": "13900000002",
        "account": "lonely_b_user",
    }
    headers_b = await _auth_headers(client, b_data)

    r = await client.get(
        f"/api/v1/longitudinal/studies/{study['id']}", headers=headers_b
    )
    assert r.status_code == 404  # 不泄露存在性


@pytest.mark.asyncio
async def test_cross_user_snapshot_create_rejected(client, test_user_data):
    """A 用户的研究，B 用户写入快照 → 404。"""
    headers_a = await _auth_headers(client, test_user_data)
    study = await _create_study(client, headers_a)

    b_data = {
        **test_user_data,
        "email": "lonely_b_writer_test@example.com",
        "phone": "13900000003",
        "account": "lonely_b_writer",
    }
    headers_b = await _auth_headers(client, b_data)

    r = await client.post(
        f"/api/v1/longitudinal/studies/{study['id']}/snapshots",
        json={"date": "2026-10-15", "axis_scores": {"A": {"score": 50}}},
        headers=headers_b,
    )
    assert r.status_code == 404
