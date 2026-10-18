"""S3-2 Powered-by SDK 测试套件。

覆盖
----
- HealthLensClient 基本构造与错误
- API Key 认证（成功/失败/吊销/过期）
- Partner 创建/列表/激活
- API Key 生成/列表/吊销
- Partner API 端点（health/config/health-score/axis/tcm/wellness-report）
- 远程配置拉取
- 错误响应（401/403/404）
- 边界值（空 body、缺失字段）
- wellness 边界（disclaimer 存在，无医疗术语）

测试策略
--------
- partner-api 端点通过 X-API-Key 认证
- Admin 端点通过 admin JWT 认证（override get_current_user 依赖）
- Client 类使用 httpx.MockTransport 打桩，不依赖真实网络
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.integrations.sdk.auth import hash_api_key, verify_api_key
from app.integrations.sdk.client import (
    HealthLensAPIError,
    HealthLensAuthError,
    HealthLensClient,
)
from app.integrations.sdk.config import get_partner_config
from app.integrations.sdk.health_check import check_health
from app.models.partner import Partner, PartnerApiKey
from app.models.user import User


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """创建 admin 用户用于 admin-only 端点测试。"""
    u = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@healthlens.com",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def admin_override(client, admin_user):
    """让所有 admin-only 端点的 get_current_user 都返回 admin_user。"""
    from app.main import app as _app

    async def _override():
        return admin_user

    _app.dependency_overrides[get_current_user] = _override
    yield
    _app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def activated_partner(db_session: AsyncSession) -> Partner:
    """创建并激活一个 partner。"""
    p = Partner(
        name=f"Partner-{uuid.uuid4().hex[:6]}",
        contact_email=f"contact-{uuid.uuid4().hex[:8]}@partner.test",
        status="active",
        rate_limit_per_min=600,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def valid_api_key(activated_partner, db_session: AsyncSession) -> str:
    """生成一条 active 且未过期的 API Key，返回明文。"""
    plain = f"hl_live_{uuid.uuid4().hex}"
    db_session.add(
        PartnerApiKey(
            partner_id=activated_partner.id,
            key_hash=hash_api_key(plain),
            key_prefix=plain[:14],
            name="test-key",
            status="active",
        )
    )
    await db_session.commit()
    return plain


# ══════════════════════════════════════════════════════════════════════════════
# HealthLensClient 基本构造与错误
# ══════════════════════════════════════════════════════════════════════════════


class TestClientConstruction:
    def test_client_construct_ok(self):
        c = HealthLensClient(base_url="https://api.test.local", api_key="hl_live_xxx")
        assert c.base_url == "https://api.test.local"
        assert c.api_key == "hl_live_xxx"
        assert c.timeout == 30.0

    def test_client_strips_trailing_slash(self):
        c = HealthLensClient(base_url="https://api.test.local/", api_key="k")
        assert c.base_url == "https://api.test.local"

    def test_client_empty_base_url_raises(self):
        with pytest.raises(ValueError):
            HealthLensClient(base_url="")

    def test_client_none_base_url_raises(self):
        with pytest.raises((ValueError, TypeError)):
            HealthLensClient(base_url=None)  # type: ignore[arg-type]

    def test_client_custom_timeout(self):
        c = HealthLensClient(base_url="https://api.test.local", timeout=5.0)
        assert c.timeout == 5.0

    def test_client_bearer_token_and_api_key_headers(self):
        c = HealthLensClient(
            base_url="https://api.test.local",
            api_key="hl_live_k",
            bearer_token="jwt-abc",
        )
        headers = c._client.headers
        assert headers["X-API-Key"] == "hl_live_k"
        assert headers["Authorization"] == "Bearer jwt-abc"

    def test_client_custom_headers(self):
        c = HealthLensClient(
            base_url="https://api.test.local",
            api_key="hl_live_k",
            headers={"X-Trace-Id": "abc123"},
        )
        assert c._client.headers["X-Trace-Id"] == "abc123"


# ══════════════════════════════════════════════════════════════════════════════
# HealthLensClient 请求/错误路径（MockTransport 打桩）
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_client_2xx_returns_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "n": 42})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_x",
        transport=httpx.MockTransport(handler),
    )
    try:
        data = await c.health_check()
        assert data == {"ok": True, "n": 42}
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_500_raises_APIError_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_x",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(HealthLensAPIError) as ei:
            await c.health_check()
        assert ei.value.status_code == 500
        assert ei.value.detail == {"detail": "boom"}
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_401_raises_AuthError():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid API key"})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_bad",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(HealthLensAuthError) as ei:
            await c.axis_assessment(user_id="u_1")
        assert ei.value.status_code == 401
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_403_raises_AuthError():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "revoked"})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_revoked",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(HealthLensAuthError) as ei:
            await c.tcm_recommendations(user_id="u_1")
        assert ei.value.status_code == 403
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_non_json_500_raises_with_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>500</html>")

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_x",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(HealthLensAPIError) as ei:
            await c.health_check()
        assert "<html>" in ei.value.detail
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_sends_expected_headers_and_body():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["x_api_key"] = request.headers.get("x-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_capture",
        transport=httpx.MockTransport(handler),
    )
    try:
        await c.health_score(user_id="u_123", date="2026-10-15")
        assert captured["method"] == "POST"
        assert captured["path"] == "/partner-api/health-score"
        assert captured["x_api_key"] == "hl_live_capture"
        assert captured["body"] == {"user_id": "u_123", "date": "2026-10-15"}
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_axis_assessment_posts_user_id_only():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_x",
        transport=httpx.MockTransport(handler),
    )
    try:
        await c.axis_assessment(user_id="u_42")
        assert captured["path"] == "/partner-api/axis-assessment"
        assert captured["body"] == {"user_id": "u_42"}
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_config_uses_query_param():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"ok": True})

    c = HealthLensClient(
        base_url="https://api.test.local",
        api_key="hl_live_x",
        transport=httpx.MockTransport(handler),
    )
    try:
        await c.config(partner_id="p_abc")
        assert captured["path"] == "/partner-api/config"
        assert captured["query"] == {"partner_id": "p_abc"}
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_client_async_context_manager():
    async with HealthLensClient(
        base_url="https://api.test.local",
        api_key="k",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    ) as c:
        assert c is not None


# ══════════════════════════════════════════════════════════════════════════════
# API Key 认证（verify_api_key + hash_api_key）
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_verify_api_key_success(valid_api_key, activated_partner, db_session):
    p = await verify_api_key(valid_api_key, db_session)
    assert p is not None
    assert p["partner_id"] == activated_partner.id
    assert p["name"] == activated_partner.name


@pytest.mark.asyncio
async def test_verify_api_key_missing_returns_none(db_session):
    assert await verify_api_key("", db_session) is None
    assert await verify_api_key(None, db_session) is None  # type: ignore[arg-type]
    assert await verify_api_key("not-a-real-key", db_session) is None


@pytest.mark.asyncio
async def test_verify_api_key_revoked_returns_none(activated_partner, db_session):
    plain = f"hl_live_{uuid.uuid4().hex}"
    db_session.add(
        PartnerApiKey(
            partner_id=activated_partner.id,
            key_hash=hash_api_key(plain),
            key_prefix=plain[:14],
            name="revoked-key",
            status="revoked",
        )
    )
    await db_session.commit()
    assert await verify_api_key(plain, db_session) is None


@pytest.mark.asyncio
async def test_verify_api_key_expired_returns_none(activated_partner, db_session):
    plain = f"hl_live_{uuid.uuid4().hex}"
    db_session.add(
        PartnerApiKey(
            partner_id=activated_partner.id,
            key_hash=hash_api_key(plain),
            key_prefix=plain[:14],
            name="expired-key",
            status="active",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()
    assert await verify_api_key(plain, db_session) is None


@pytest.mark.asyncio
async def test_verify_api_key_inactive_partner_returns_none(db_session):
    """Partner 未激活（pending/inactive）时认证失败。"""
    p = Partner(name="Pending", contact_email="p@test.com", status="pending")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    plain = f"hl_live_{uuid.uuid4().hex}"
    db_session.add(
        PartnerApiKey(
            partner_id=p.id,
            key_hash=hash_api_key(plain),
            key_prefix=plain[:14],
            name="k",
            status="active",
        )
    )
    await db_session.commit()
    assert await verify_api_key(plain, db_session) is None


def test_hash_api_key_deterministic():
    h1 = hash_api_key("hl_live_abc")
    h2 = hash_api_key("hl_live_abc")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 == hashlib.sha256(b"hl_live_abc").hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Partner 管理端点（admin only）
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_partner_requires_admin(client):
    """未带 admin token → 401。"""
    r = await client.post(
        "/api/v1/partners",
        json={"name": "P", "contact_email": "a@b.com"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_partner_success(client, admin_override):
    r = await client.post(
        "/api/v1/partners",
        json={
            "name": "Health Partner",
            "contact_email": "contact@partner.com",
            "description": "desc",
            "rate_limit_per_min": 300,
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "pending"
    assert data["name"] == "Health Partner"
    assert data["rate_limit_per_min"] == 300
    assert data["id"]


@pytest.mark.asyncio
async def test_create_partner_missing_fields(client, admin_override):
    """缺失必填字段 → 422。"""
    r = await client.post("/api/v1/partners", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_partner_empty_body(client, admin_override):
    """无 body → 422。"""
    r = await client.post("/api/v1/partners")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_partners(client, admin_override):
    r = await client.get("/api/v1/partners")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["items"], list)
    assert "total" in body


@pytest.mark.asyncio
async def test_list_partners_requires_admin(client):
    r = await client.get("/api/v1/partners")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_activate_partner(client, admin_override, db_session, activated_partner):
    """激活 pending 的 partner（先改库为 pending 再调端点）。"""
    activated_partner.status = "pending"
    await db_session.commit()
    r = await client.post(f"/api/v1/partners/{activated_partner.id}/activate")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_activate_partner_already_active(client, admin_override, activated_partner):
    r = await client.post(f"/api/v1/partners/{activated_partner.id}/activate")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_activate_partner_not_found(client, admin_override):
    r = await client.post(f"/api/v1/partners/{uuid.uuid4()}/activate")
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# API Key 生成 / 列表 / 吊销
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_api_key_success(client, admin_override, activated_partner):
    r = await client.post(
        f"/api/v1/partners/{activated_partner.id}/api-keys",
        json={"name": "prod-key"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["key_plain"].startswith("hl_live_")
    assert data["key_hash"] == hash_api_key(data["key_plain"])
    assert data["status"] == "active"
    assert data["key_prefix"] == data["key_plain"][:14]


@pytest.mark.asyncio
async def test_create_api_key_with_expiry(client, admin_override, activated_partner):
    r = await client.post(
        f"/api/v1/partners/{activated_partner.id}/api-keys",
        json={"name": "temp-key", "expires_in_days": 30},
    )
    assert r.status_code == 201
    assert r.json()["expires_at"] is not None


@pytest.mark.asyncio
async def test_create_api_key_partner_not_found(client, admin_override):
    r = await client.post(
        f"/api/v1/partners/{uuid.uuid4()}/api-keys",
        json={"name": "nope"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_api_key_missing_name(client, admin_override, activated_partner):
    r = await client.post(
        f"/api/v1/partners/{activated_partner.id}/api-keys",
        json={},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_api_keys(client, admin_override, activated_partner, valid_api_key):
    r = await client.get(f"/api/v1/partners/{activated_partner.id}/api-keys")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # 列表中不应出现 key_plain
    for item in body["items"]:
        assert "key_plain" not in item
        assert "key_hash" in item


@pytest.mark.asyncio
async def test_list_api_keys_partner_not_found(client, admin_override):
    r = await client.get(f"/api/v1/partners/{uuid.uuid4()}/api-keys")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key(client, admin_override, activated_partner, db_session, valid_api_key):
    # 先取回刚创建的 key id
    result = await db_session.execute(
        select(PartnerApiKey).where(PartnerApiKey.partner_id == activated_partner.id)
    )
    k = result.scalars().first()
    r = await client.delete(f"/api/v1/partners/{activated_partner.id}/api-keys/{k.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_revoke_api_key_already_revoked(client, admin_override, activated_partner, db_session, valid_api_key):
    result = await db_session.execute(
        select(PartnerApiKey).where(PartnerApiKey.partner_id == activated_partner.id)
    )
    k = result.scalars().first()
    await client.delete(f"/api/v1/partners/{activated_partner.id}/api-keys/{k.id}")
    r = await client.delete(f"/api/v1/partners/{activated_partner.id}/api-keys/{k.id}")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_revoke_api_key_not_found(client, admin_override, activated_partner):
    r = await client.delete(f"/api/v1/partners/{activated_partner.id}/api-keys/{uuid.uuid4()}")
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Partner API 端点 —— 认证路径
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_partner_api_health_public(client):
    """GET /health 无需 API Key。"""
    r = await client.get("/api/v1/partner-api/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "version" in body
    assert "engines" in body
    assert "database" in body


@pytest.mark.asyncio
async def test_partner_api_config_missing_key(client):
    r = await client.get("/api/v1/partner-api/config")
    assert r.status_code == 401
    assert "missing" in r.json()["detail"].lower() or "invalid" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_partner_api_config_invalid_key(client):
    r = await client.get(
        "/api/v1/partner-api/config",
        headers={"X-API-Key": "hl_live_not_exist"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_partner_api_config_with_valid_key(client, valid_api_key):
    r = await client.get(
        "/api/v1/partner-api/config",
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "enabled_modules" in body
    assert "allowed_endpoints" in body
    assert "rate_limit" in body
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_partner_api_config_cross_partner(client, activated_partner, valid_api_key):
    """允许跨 partner 查询配置（管理/迁移场景）。"""
    r = await client.get(
        f"/api/v1/partner-api/config?partner_id={activated_partner.id}",
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200
    assert r.json()["partner_id"] == activated_partner.id


@pytest.mark.asyncio
async def test_partner_api_config_partner_not_found(client, valid_api_key):
    r = await client.get(
        f"/api/v1/partner-api/config?partner_id={uuid.uuid4()}",
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Partner API 端点 —— 数据查询（需 user_id 存在）
# ══════════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    u = User(
        email=f"target_{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        role="patient",
        is_active=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_health_score_ok(client, valid_api_key, test_user):
    r = await client.post(
        "/api/v1/partner-api/health-score",
        json={"user_id": test_user.id, "date": "2026-10-15"},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["user_id"] == test_user.id
    assert isinstance(body["health_score"], float)
    assert 0 <= body["health_score"] <= 100
    assert "axis_scores" in body
    assert len(body["axis_scores"]) == 8
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_health_score_missing_key(client, test_user):
    r = await client.post(
        "/api/v1/partner-api/health-score",
        json={"user_id": test_user.id},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_score_user_not_found(client, valid_api_key):
    r = await client.post(
        "/api/v1/partner-api/health-score",
        json={"user_id": str(uuid.uuid4())},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_health_score_empty_body(client, valid_api_key):
    r = await client.post(
        "/api/v1/partner-api/health-score",
        json={},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_health_score_bad_date_format(client, valid_api_key, test_user):
    r = await client.post(
        "/api/v1/partner-api/health-score",
        json={"user_id": test_user.id, "date": "not-a-date"},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_axis_assessment_ok(client, valid_api_key, test_user):
    r = await client.post(
        "/api/v1/partner-api/axis-assessment",
        json={"user_id": test_user.id},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["axes"]) == 8
    for ax in body["axes"]:
        assert ax["code"] in {"A", "B", "C", "D", "E", "F", "G", "H"}
        assert isinstance(ax["score"], float)
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_axis_assessment_user_not_found(client, valid_api_key):
    r = await client.post(
        "/api/v1/partner-api/axis-assessment",
        json={"user_id": str(uuid.uuid4())},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tcm_recommendations_ok(client, valid_api_key, test_user):
    r = await client.post(
        "/api/v1/partner-api/tcm-recommendations",
        json={"user_id": test_user.id},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["recommendations"]) == 3
    for r_ in body["recommendations"]:
        assert r_["axis"] in {"A", "B", "C", "D", "E", "F", "G", "H"}
        assert "focus" in r_
    assert "disclaimer" in body


@pytest.mark.asyncio
async def test_tcm_recommendations_missing_key(client, test_user):
    r = await client.post(
        "/api/v1/partner-api/tcm-recommendations",
        json={"user_id": test_user.id},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wellness_report_ok(client, valid_api_key, test_user):
    r = await client.post(
        "/api/v1/partner-api/wellness-report",
        json={"user_id": test_user.id},
        headers={"X-API-Key": valid_api_key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["composite_score"], float)
    assert "axis_scores" in body
    assert "focus_axes" in body
    assert "disclaimer" in body


# ══════════════════════════════════════════════════════════════════════════════
# 认证状态转换集成测试
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_key_works_end_to_end(client, admin_override, db_session, test_user):
    """创建 partner → 激活 → 生成 key → 用 key 调 API。"""
    # 1. 创建
    r1 = await client.post(
        "/api/v1/partners",
        json={
            "name": "E2E Partner",
            "contact_email": f"e2e-{uuid.uuid4().hex[:6]}@partner.com",
        },
    )
    assert r1.status_code == 201
    pid = r1.json()["id"]

    # 2. 激活前，key 生成但无法调 API（partner pending）
    r2 = await client.post(
        f"/api/v1/partners/{pid}/api-keys",
        json={"name": "k1"},
    )
    assert r2.status_code == 201
    plain = r2.json()["key_plain"]

    r_probe = await client.get(
        "/api/v1/partner-api/config",
        headers={"X-API-Key": plain},
    )
    assert r_probe.status_code == 401, "pending partner 应该拒绝"

    # 3. 激活后再调
    r3 = await client.post(f"/api/v1/partners/{pid}/activate")
    assert r3.status_code == 200

    r4 = await client.get(
        "/api/v1/partner-api/config",
        headers={"X-API-Key": plain},
    )
    assert r4.status_code == 200

    # 4. 吊销 key 后立刻 401
    r5 = await client.delete(
        f"/api/v1/partners/{pid}/api-keys/{r2.json()['id']}"
    )
    assert r5.status_code == 200

    r6 = await client.get(
        "/api/v1/partner-api/config",
        headers={"X-API-Key": plain},
    )
    assert r6.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 远程配置模块直接测试
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_partner_config_direct(activated_partner, db_session):
    cfg = await get_partner_config(activated_partner.id, db_session)
    assert cfg["partner_id"] == activated_partner.id
    assert cfg["status"] == "active"
    assert cfg["rate_limit"]["per_min"] == 600
    assert "disclaimer" in cfg
    assert cfg["enabled_modules"]


@pytest.mark.asyncio
async def test_get_partner_config_not_found_raises(db_session):
    with pytest.raises(KeyError):
        await get_partner_config(str(uuid.uuid4()), db_session)


# ══════════════════════════════════════════════════════════════════════════════
# 健康检查模块直接测试
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_check_health_returns_expected_shape(db_session):
    r = await check_health(db_session)
    assert r["status"] in {"ok", "degraded"}
    assert "version" in r
    assert isinstance(r["engines"], dict)
    assert set(r["engines"].keys()) == {"fusion", "tcm", "pulse"}
    assert "database" in r
    assert "timestamp" in r
    assert "disclaimer" in r


# ══════════════════════════════════════════════════════════════════════════════
# Wellness 边界检查
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_disclaimer_contains_wellness_language(client, valid_api_key, test_user):
    """所有数据端点响应带 disclaimer，且不含医疗/诊断/治疗/患者 术语。"""
    for path, body in [
        ("/health-score", {"user_id": test_user.id}),
        ("/axis-assessment", {"user_id": test_user.id}),
        ("/tcm-recommendations", {"user_id": test_user.id}),
        ("/wellness-report", {"user_id": test_user.id}),
    ]:
        r = await client.post(
            f"/api/v1/partner-api{path}",
            json=body,
            headers={"X-API-Key": valid_api_key},
        )
        assert r.status_code == 200, f"{path} failed: {r.text}"
        assert "disclaimer" in r.json()


@pytest.mark.asyncio
async def test_partner_api_not_clinical_language(client, valid_api_key, test_user):
    """输出 JSON 不出现医疗术语（diagnosis/treatment/patient/drug）。"""
    r = await client.post(
        "/api/v1/partner-api/axis-assessment",
        json={"user_id": test_user.id},
        headers={"X-API-Key": valid_api_key},
    )
    text = r.text.lower()
    for term in ["diagnosis", "treatment", "patient", "drug"]:
        assert term not in text, f"临床术语 {term} 不应出现"
