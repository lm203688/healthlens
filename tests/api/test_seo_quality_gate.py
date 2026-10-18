"""SEO 发布闸门端到端测试（M14 P0-1）。

被测对象：``app/api/seo.py`` 的三条发布路径。

核心不变式：**任何一条能产出 ``status="published"`` 的路径都必须过闸门**。
闸门只接 publish 一条路径等于没接——``/pages/import`` 与 ``/pages/batch-import``
的 ``status`` 默认值都是 ``published``，是两条独立的绕过通道。
因此这里对三条路径分别断言。
"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.seo import SeoPage
from app.models.user import User
from app.utils.security import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def admin_client(db_session: AsyncSession):
    """管理员客户端：直接建 admin 用户并签发 token。"""
    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@healthlens.com",
        password_hash="x",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token({"sub": user.id, "email": user.email})

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac, db_session
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def patient_client(db_session: AsyncSession):
    """普通用户客户端（非 admin）。"""
    user = User(
        email=f"patient_{uuid.uuid4().hex[:8]}@healthlens.com",
        password_hash="x",
        role="patient",
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token({"sub": user.id, "email": user.email})

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac, db_session
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 内容样例
# ---------------------------------------------------------------------------

def _placeholder_html() -> str:
    """`POST /pages/generate` 实际产出的占位页形态。"""
    return "<h1>生姜</h1><p>正在生成中...</p>"


def _compliant_html() -> str:
    """一份能过闸门的完整页面。"""
    filler = ("健康生活方式的长期积累对整体状态有积极影响，值得持续关注。" * 15)
    return (
        '<!DOCTYPE html><html><head>'
        '<meta name="description" content="测试页面描述">'
        '<link rel="canonical" href="https://healthlens.cc/test">'
        '</head><body>'
        '<h1>测试标题</h1>'
        f'<h2>小节一</h2><p>{filler}</p>'
        f'<h2>小节二</h2><p>{filler}</p>'
        '<script type="application/ld+json">'
        '{"@type": "Article", "@context": "https://schema.org"}'
        '</script>'
        '<script type="application/ld+json">{"@type": "FAQPage"}</script>'
        '<script type="application/ld+json">{"@type": "MedicalWebPage"}</script>'
        '<p>本文为养生参考，不构成医疗建议。</p>'
        '</body></html>'
    )


async def _make_page(db_session: AsyncSession, slug: str, content_html: str) -> SeoPage:
    page = SeoPage(
        slug=slug,
        title="测试标题",
        meta_description="测试页面描述",
        meta_keywords="",
        content_html=content_html,
        category="general",
        keywords="",
        status="draft",
        word_count=0,
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


async def _get_status(db_session: AsyncSession, slug: str) -> str:
    from sqlalchemy import select
    result = await db_session.execute(select(SeoPage).where(SeoPage.slug == slug))
    page = result.scalar_one_or_none()
    return page.status if page else None


async def _get_record(db_session: AsyncSession, slug: str) -> dict:
    from sqlalchemy import select
    result = await db_session.execute(select(SeoPage).where(SeoPage.slug == slug))
    page = result.scalar_one_or_none()
    if not page or not isinstance(page.structured_data, dict):
        return {}
    return page.structured_data.get("quality_gate", {}) or {}


# ---------------------------------------------------------------------------
# 1. POST /pages/publish/{slug}
# ---------------------------------------------------------------------------

class TestPublishGate:
    @pytest.mark.asyncio
    async def test_placeholder_page_blocked(self, admin_client):
        """占位页发布必须被拦：422 + 状态不变 + 留痕。"""
        ac, db = admin_client
        slug = f"ph-{uuid.uuid4().hex[:8]}"
        await _make_page(db, slug, _placeholder_html())

        r = await ac.post(f"/api/v1/seo/pages/publish/{slug}")
        assert r.status_code == 422, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "quality_gate_blocked"
        assert "critical_issues" in detail and detail["critical_issues"]
        assert detail["score"] < 100

        # 状态绝不能变成 published
        assert await _get_status(db, slug) == "draft"
        # 被拦记录必须留痕，outcome=blocked
        record = await _get_record(db, slug)
        assert record, "blocked attempt must be recorded for audit"
        assert record["passed"] is False
        assert record["outcome"] == "blocked"

    @pytest.mark.asyncio
    async def test_compliant_page_published(self, admin_client):
        """合规页必须能正常发布（闸门不得死锁发布流程）。"""
        ac, db = admin_client
        slug = f"ok-{uuid.uuid4().hex[:8]}"
        await _make_page(db, slug, _compliant_html())

        r = await ac.post(f"/api/v1/seo/pages/publish/{slug}")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "published"
        assert r.json()["data"]["quality_gate"]["passed"] is True

        assert await _get_status(db, slug) == "published"
        record = await _get_record(db, slug)
        assert record["outcome"] == "published"
        assert record["passed"] is True

    @pytest.mark.asyncio
    async def test_missing_page_returns_404(self, admin_client):
        ac, _ = admin_client
        r = await ac.post("/api/v1/seo/pages/publish/does-not-exist")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_patient_cannot_publish(self, patient_client):
        ac, db = patient_client
        slug = f"p-{uuid.uuid4().hex[:8]}"
        await _make_page(db, slug, _compliant_html())
        r = await ac.post(f"/api/v1/seo/pages/publish/{slug}")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# 2. POST /pages/{slug}/review —— 只预检不改状态
# ---------------------------------------------------------------------------

class TestReviewEndpoint:
    @pytest.mark.asyncio
    async def test_review_does_not_publish(self, admin_client):
        ac, db = admin_client
        slug = f"rv-{uuid.uuid4().hex[:8]}"
        await _make_page(db, slug, _compliant_html())

        r = await ac.post(f"/api/v1/seo/pages/review/{slug}")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["passed"] is True
        # 预检不得改变发布状态
        assert await _get_status(db, slug) == "draft"
        assert (await _get_record(db, slug))["outcome"] == "review_only"

    @pytest.mark.asyncio
    async def test_review_reports_blocker(self, admin_client):
        ac, db = admin_client
        slug = f"rv-{uuid.uuid4().hex[:8]}"
        await _make_page(db, slug, _placeholder_html())

        r = await ac.post(f"/api/v1/seo/pages/review/{slug}")
        assert r.status_code == 200
        assert r.json()["data"]["passed"] is False
        assert r.json()["data"]["critical_issues"]


# ---------------------------------------------------------------------------
# 3. POST /pages/import —— 绕过通道之一
# ---------------------------------------------------------------------------

class TestImportGate:
    @pytest.mark.asyncio
    async def test_import_published_placeholder_blocked(self, admin_client):
        """status=published 的 import 必须过闸门，否则这是第二条发布通道。"""
        ac, db = admin_client
        slug = f"im-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/import", json={
            "slug": slug,
            "title": "测试",
            "content_html": _placeholder_html(),
            "status": "published",
        })
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "quality_gate_blocked"
        # 页面不得被创建
        assert await _get_status(db, slug) is None

    @pytest.mark.asyncio
    async def test_import_draft_placeholder_allowed(self, admin_client):
        """draft 不上线，草稿态无需质量约束。"""
        ac, db = admin_client
        slug = f"im-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/import", json={
            "slug": slug,
            "title": "测试",
            "content_html": _placeholder_html(),
            "status": "draft",
        })
        assert r.status_code == 200, r.text
        assert await _get_status(db, slug) == "draft"

    @pytest.mark.asyncio
    async def test_import_default_status_is_gated(self, admin_client):
        """`status` 默认值为 published，所以不传 status 也必须过闸门。"""
        ac, db = admin_client
        slug = f"im-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/import", json={
            "slug": slug,
            "title": "测试",
            "content_html": _placeholder_html(),
            # status 省略 → 默认 published
        })
        assert r.status_code == 422
        assert await _get_status(db, slug) is None

    @pytest.mark.asyncio
    async def test_import_compliant_published(self, admin_client):
        ac, db = admin_client
        slug = f"im-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/import", json={
            "slug": slug,
            "title": "测试",
            "content_html": _compliant_html(),
            "status": "published",
        })
        assert r.status_code == 200, r.text
        assert await _get_status(db, slug) == "published"


# ---------------------------------------------------------------------------
# 4. POST /pages/batch-import —— 绕过通道之二
# ---------------------------------------------------------------------------

class TestBatchImportGate:
    @pytest.mark.asyncio
    async def test_batch_blocks_bad_keeps_good(self, admin_client):
        """批量导入必须逐项拦截：坏的记入 failed，好的照常创建。"""
        ac, db = admin_client
        bad = f"bb-{uuid.uuid4().hex[:8]}"
        good = f"bg-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/batch-import", json={
            "pages": [
                {
                    "slug": bad,
                    "title": "占位页",
                    "content_html": _placeholder_html(),
                    "status": "published",
                },
                {
                    "slug": good,
                    "title": "合规页",
                    "content_html": _compliant_html(),
                    "status": "published",
                },
            ]
        })
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["created"] == 1
        assert len(data["failed"]) == 1
        assert data["failed"][0]["slug"] == bad
        assert data["failed"][0]["error"] == "quality_gate_blocked"

        # 好的已发布，坏的未被创建
        assert await _get_status(db, good) == "published"
        assert await _get_status(db, bad) is None

    @pytest.mark.asyncio
    async def test_batch_default_status_is_gated(self, admin_client):
        ac, db = admin_client
        slug = f"bg-{uuid.uuid4().hex[:8]}"

        r = await ac.post("/api/v1/seo/pages/batch-import", json={
            "pages": [{
                "slug": slug,
                "title": "测试",
                "content_html": _placeholder_html(),
                # status 省略 → 默认 published → 必须过闸门
            }]
        })
        assert r.status_code == 200
        assert len(r.json()["data"]["failed"]) == 1
        assert await _get_status(db, slug) is None
