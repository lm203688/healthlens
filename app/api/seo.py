"""SEO 内容管理 API
路由前缀: /api/v1/seo
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from loguru import logger

from app.database import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.seo import SeoPage, SeoPageTemplate, KeywordCluster
from app.lib.seo_quality_gate import QualityGateResult, run_quality_gate

router = APIRouter()


# ---------------------------------------------------------------------------
# 发布质量闸门（M14 P0-1）
# ---------------------------------------------------------------------------
# 三条发布路径必须全部经过闸门，否则闸门等于不存在：
#   1. POST /pages/publish/{slug}      —— 单独发布
#   2. POST /pages/import              —— UPSERT，status 默认 published
#   3. POST /pages/batch-import        —— 批量 UPSERT，status 默认 published
#
# 背景缺陷：闸门模块 app/lib/seo_quality_gate.py 此前**已存在但全仓零调用**，
# 三条发布路径都不跑校验，占位页（"正在生成中..."、word_count=0）可被一键
# 发布到公开站点。健康内容属 YMYL，低质批量页是负资产。此处接线并 fail-closed。
#
# 闸门结果写入 SeoPage.structured_data["quality_gate"]（复用既有 JSON 列，
# 不新增表结构、不引入迁移），使「哪一版内容在何时被拦/放行」可事后审计。

GATE_RECORD_KEY = "quality_gate"


def _gate_payload(gate: QualityGateResult) -> dict:
    """把闸门结果压成可序列化的响应体。"""
    return {
        "passed": gate.passed,
        "score": gate.score,
        "critical_count": len(gate.critical_issues),
        "warning_count": len(gate.warnings),
        "critical_issues": list(gate.critical_issues),
        "warnings": list(gate.warnings),
        "checks": [
            {
                "check_name": c.check_name,
                "status": c.status.value,
                "message": c.message,
                "details": list(c.details),
            }
            for c in gate.checks
        ],
    }


def _gate_record(gate: QualityGateResult, actor_id: str, outcome: str) -> dict:
    """可写入 JSON 列的闸门审计记录。outcome: blocked|published|review_only"""
    return {
        "passed": gate.passed,
        "score": gate.score,
        "checked_at": datetime.utcnow().isoformat(),
        "actor_id": actor_id,
        "outcome": outcome,
        "critical_issues": list(gate.critical_issues),
        "warnings": list(gate.warnings),
    }


def _merge_gate_record(page: SeoPage, record: dict) -> None:
    """把闸门记录并入 structured_data，保留既有的 JSON-LD 等结构化数据。"""
    current = page.structured_data if isinstance(page.structured_data, dict) else {}
    current[GATE_RECORD_KEY] = record
    page.structured_data = current


def _block_detail(gate: QualityGateResult) -> dict:
    """闸门拦截时的 422 detail：必须给出具体的、可修复的原因。"""
    return {
        "code": "quality_gate_blocked",
        "message": f"质量闸门未通过（评分 {gate.score}/100），已拦截发布",
        "score": gate.score,
        "critical_issues": list(gate.critical_issues),
        "warnings": list(gate.warnings),
        "hint": "修复上述 blocker 后重试；可用 POST /pages/review/{slug} 预检",
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    """批量生成 SEO 页面请求"""
    count: int = Field(default=5, ge=1, le=50)
    category: Optional[str] = Field(default=None, max_length=50)


class SeoPageImport(BaseModel):
    """导入单个 SEO 页面"""
    slug: str = Field(..., max_length=200)
    title: str = Field(..., max_length=500)
    meta_description: Optional[str] = Field(default="", max_length=1000)
    meta_keywords: Optional[str] = Field(default="", max_length=500)
    content_html: str
    structured_data: Optional[dict] = None
    category: Optional[str] = Field(default="general", max_length=100)
    heading: Optional[str] = Field(default=None, max_length=500)
    keywords: Optional[str] = ""
    word_count: Optional[int] = 0
    status: Optional[str] = "published"


class SeoPageBatchImport(BaseModel):
    """批量导入 SEO 页面"""
    pages: list[SeoPageImport] = Field(..., max_length=50)


class KeywordClusterCreate(BaseModel):
    """关键词集群创建"""
    keyword: str = Field(..., max_length=200)
    category: Optional[str] = Field(default=None, max_length=50)
    search_volume: Optional[int] = Field(default=0, ge=0)
    difficulty: Optional[int] = Field(default=0, ge=0, le=100)
    related_keywords: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# GET /pages - 分页列表
# ---------------------------------------------------------------------------

@router.get("/pages", summary="获取 SEO 页面列表")
async def list_seo_pages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页获取 SEO 页面，支持按 category / status 筛选"""
    query = select(SeoPage)
    count_query = select(func.count()).select_from(SeoPage)

    if category:
        query = query.where(SeoPage.category == category)
        count_query = count_query.where(SeoPage.category == category)
    if status:
        query = query.where(SeoPage.status == status)
        count_query = count_query.where(SeoPage.status == status)

    query = query.order_by(SeoPage.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    pages = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for p in pages:
        data.append({
            "id": str(p.id),
            "slug": p.slug,
            "title": p.title,
            "category": p.category,
            "status": p.status,
            "meta_description": p.meta_description,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


# ---------------------------------------------------------------------------
# GET /pages/{slug} - 单页面详情
# ---------------------------------------------------------------------------

@router.get("/pages/{slug}", summary="获取 SEO 页面详情")
async def get_seo_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(SeoPage).where(SeoPage.slug == slug)
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="SEO page not found")

    return {
        "success": True,
        "data": {
            "id": str(page.id),
            "slug": page.slug,
            "title": page.title,
            "category": page.category,
            "status": page.status,
            "meta_description": page.meta_description,
            "meta_keywords": page.meta_keywords,
            "content_html": page.content_html,
            "word_count": page.word_count,
            "created_at": page.created_at.isoformat() if page.created_at else None,
            "updated_at": page.updated_at.isoformat() if page.updated_at else None,
            "published_at": page.published_at.isoformat() if page.published_at else None,
        },
    }


# ---------------------------------------------------------------------------
# POST /pages/generate - 批量生成 (admin only)
# ---------------------------------------------------------------------------

@router.post("/pages/generate", summary="批量生成 SEO 页面 (管理员)")
async def generate_seo_pages(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """管理员触发批量 SEO 页面生成。从 KeywordCluster 中选取关键词，
    依次创建 SeoPage 记录（status=draft）。"""
    # 查找可用的关键词
    kw_query = select(KeywordCluster).order_by(KeywordCluster.search_volume.desc())
    if body.category:
        kw_query = kw_query.where(KeywordCluster.category == body.category)
    kw_query = kw_query.limit(body.count)

    kw_result = await db.execute(kw_query)
    keywords = kw_result.scalars().all()

    if not keywords:
        raise HTTPException(status_code=404, detail="没有可用的关键词来生成页面")

    created = []
    for kw in keywords:
        slug = kw.keyword.lower().replace(" ", "-").replace("/", "-")[:120]
        # 检查是否已存在
        exists = await db.execute(
            select(SeoPage).where(SeoPage.slug == slug)
        )
        if exists.scalar_one_or_none():
            logger.info(f"SEO page already exists for slug: {slug}, skipping")
            continue

        seo_page = SeoPage(
            slug=slug,
            title=kw.keyword,
            category=kw.category or "general",
            status="draft",
            meta_description=f"了解{kw.keyword}的全面健康知识，HealthLens 为您提供专业解读。",
            meta_keywords=kw.keyword,
            content_html=f"<h1>{kw.keyword}</h1><p>正在生成中...</p>",
            word_count=0,
        )
        db.add(seo_page)
        created.append({"slug": slug, "title": kw.keyword})

    await db.commit()
    logger.info(f"Admin {current_user.id} triggered SEO generation: {len(created)} pages")

    return {
        "success": True,
        "message": f"成功生成 {len(created)} 个 SEO 页面草稿",
        "data": created,
    }


# ---------------------------------------------------------------------------
# POST /pages/publish/{slug} - 发布页面 (admin only)
# ---------------------------------------------------------------------------

@router.post("/pages/review/{slug}", summary="SEO 页面发布前质量预检 (管理员)")
async def review_seo_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """跑质量闸门但**不改变 status**。

    用途：让管理员在 publish 前看到「为什么不能发」，而不是反复试 publish。
    闸门自身异常时 run_quality_gate 内部按 blocker 处理（fail-closed），
    本端点不会返回假通过。
    """
    result = await db.execute(select(SeoPage).where(SeoPage.slug == slug))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="SEO page not found")

    gate = run_quality_gate(page.content_html, slug=page.slug)
    _merge_gate_record(page, _gate_record(gate, current_user.id, "review_only"))
    await db.commit()

    logger.info(
        f"Admin {current_user.id} reviewed SEO page '{slug}': "
        f"passed={gate.passed} score={gate.score}"
    )
    return {
        "success": True,
        "message": f"预检完成：{'可发布' if gate.passed else '存在 blocker，不可发布'}",
        "data": _gate_payload(gate),
    }


@router.post("/pages/publish/{slug}", summary="发布 SEO 页面 (管理员)")
async def publish_seo_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """发布页面。发布前必须通过质量闸门，未通过返回 422 且不改变状态。"""
    result = await db.execute(select(SeoPage).where(SeoPage.slug == slug))
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="SEO page not found")

    # ── 发布闸门（fail-closed）──────────────────────────────────
    gate = run_quality_gate(page.content_html, slug=page.slug)
    if not gate.passed:
        # 被拦的闸门结果同样留痕：记录「谁在何时因何被拦」，便于事后审计。
        _merge_gate_record(page, _gate_record(gate, current_user.id, "blocked"))
        await db.commit()
        logger.warning(
            f"Admin {current_user.id} publish BLOCKED for '{slug}': "
            f"score={gate.score}, critical={len(gate.critical_issues)}"
        )
        raise HTTPException(status_code=422, detail=_block_detail(gate))

    page.status = "published"
    page.published_at = datetime.utcnow()
    _merge_gate_record(page, _gate_record(gate, current_user.id, "published"))
    await db.commit()
    await db.refresh(page)

    logger.info(
        f"Admin {current_user.id} published SEO page: {slug} "
        f"(gate passed, score={gate.score})"
    )

    return {
        "success": True,
        "message": f"页面 '{slug}' 已发布",
        "data": {
            "slug": page.slug,
            "status": page.status,
            "published_at": page.published_at.isoformat() if page.published_at else None,
            "quality_gate": _gate_payload(gate),
        },
    }


# ---------------------------------------------------------------------------
# GET /keywords - 关键词列表
# ---------------------------------------------------------------------------

@router.get("/keywords", summary="获取关键词集群列表")
async def list_keywords(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(KeywordCluster)
    count_query = select(func.count()).select_from(KeywordCluster)

    if category:
        query = query.where(KeywordCluster.category == category)
        count_query = count_query.where(KeywordCluster.category == category)

    query = query.order_by(KeywordCluster.search_volume.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    keywords = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for kw in keywords:
        data.append({
            "id": str(kw.id),
            "keyword": kw.keyword,
            "category": kw.category,
            "search_volume": kw.search_volume,
            "difficulty": kw.difficulty,
            "related_keywords": kw.related_keywords or [],
            "created_at": kw.created_at.isoformat() if kw.created_at else None,
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


# ---------------------------------------------------------------------------
# POST /keywords - 新增关键词集群
# ---------------------------------------------------------------------------

@router.post("/keywords", summary="添加关键词集群")
async def create_keyword(
    body: KeywordClusterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kw = KeywordCluster(
        keyword=body.keyword,
        category=body.category,
        search_volume=body.search_volume,
        difficulty=body.difficulty,
        related_keywords=body.related_keywords or [],
    )
    db.add(kw)
    await db.commit()
    await db.refresh(kw)

    return {
        "success": True,
        "message": "关键词集群已添加",
        "data": {
            "id": str(kw.id),
            "keyword": kw.keyword,
            "category": kw.category,
        },
    }


# ---------------------------------------------------------------------------
# GET /stats - SEO 统计数据
# ---------------------------------------------------------------------------

@router.get("/stats", summary="获取 SEO 统计数据")
async def get_seo_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 总页面数
    total_result = await db.execute(
        select(func.count()).select_from(SeoPage)
    )
    total_pages = total_result.scalar() or 0

    # 已发布数
    published_result = await db.execute(
        select(func.count()).select_from(SeoPage).where(SeoPage.status == "published")
    )
    published_pages = published_result.scalar() or 0

    # 草稿数
    draft_result = await db.execute(
        select(func.count()).select_from(SeoPage).where(SeoPage.status == "draft")
    )
    draft_pages = draft_result.scalar() or 0

    # 分类分布
    cat_result = await db.execute(
        select(SeoPage.category, func.count().label("count"))
        .group_by(SeoPage.category)
    )
    categories = []
    for row in cat_result:
        categories.append({"category": row.category, "count": row.count})

    # 关键词总数
    kw_total_result = await db.execute(
        select(func.count()).select_from(KeywordCluster)
    )
    total_keywords = kw_total_result.scalar() or 0

    return {
        "success": True,
        "data": {
            "total_pages": total_pages,
            "published_pages": published_pages,
            "draft_pages": draft_pages,
            "categories": categories,
            "total_keywords": total_keywords,
        },
    }


# ---------------------------------------------------------------------------
# GET /sitemap - 动态生成 sitemap XML
# ---------------------------------------------------------------------------

@router.get("/sitemap", summary="生成 sitemap XML")
async def get_sitemap(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import Response

    result = await db.execute(
        select(SeoPage).where(SeoPage.status == "published")
    )
    pages = result.scalars().all()

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"')
    xml_lines.append('        xmlns:xhtml="http://www.w3.org/1999/xhtml">')

    def _en_title(p: SeoPage) -> str | None:
        """页面是否存在真实英文译本（structured_data.i18n.en.title）。"""
        sd = p.structured_data or {}
        if not isinstance(sd, dict):
            return None
        i18n = sd.get("i18n") or {}
        if not isinstance(i18n, dict):
            return None
        en = i18n.get("en")
        if isinstance(en, dict) and (en.get("title") or "").strip():
            return en["title"]
        return None

    for p in pages:
        lastmod = (p.updated_at or p.created_at).strftime("%Y-%m-%d") if (p.updated_at or p.created_at) else datetime.utcnow().strftime("%Y-%m-%d")
        zh_url = f"https://healthlens.cc/knowledge/{p.slug}"
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{zh_url}</loc>")
        # 只为真实存在的英文译本输出 alternate —— 绝不指向不存在的页面
        if _en_title(p):
            en_url = f"https://healthlens.cc/en/knowledge/{p.slug}"
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="zh-CN" href="{zh_url}"/>')
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="en" href="{en_url}"/>')
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{zh_url}"/>')
        xml_lines.append(f"    <lastmod>{lastmod}</lastmod>")
        xml_lines.append("    <changefreq>weekly</changefreq>")
        xml_lines.append("    <priority>0.7</priority>")
        xml_lines.append("  </url>")

    xml_content = "\n".join(xml_lines)

    return FastAPIResponse(content=xml_content, media_type="application/xml")


# ---------------------------------------------------------------------------
# POST /pages/import - 创建或更新单个 SEO 页面 (admin only)
# ---------------------------------------------------------------------------

@router.post("/pages/import", summary="导入单个 SEO 页面 (管理员)")
async def import_seo_page(
    body: SeoPageImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建或更新一个 SEO 页面（UPSERT by slug）

    目标状态为 published 时必须先过质量闸门——否则这是绕过 publish 闸门的
    第二条通道（`status` 默认为 published）。draft/archived 不拦：草稿态
    不上线，无需质量约束。
    """
    result = await db.execute(
        select(SeoPage).where(SeoPage.slug == body.slug)
    )
    page = result.scalar_one_or_none()
    now = datetime.utcnow()

    target_status = body.status or "published"
    if target_status == "published":
        gate = run_quality_gate(body.content_html, slug=body.slug)
        if not gate.passed:
            logger.warning(
                f"Admin {current_user.id} import BLOCKED for '{body.slug}': "
                f"score={gate.score}, critical={len(gate.critical_issues)}"
            )
            raise HTTPException(
                status_code=422,
                detail=_block_detail(gate),
            )

    if page:
        page.title = body.title
        page.meta_description = body.meta_description or ""
        page.meta_keywords = body.meta_keywords or ""
        page.content_html = body.content_html
        page.structured_data = body.structured_data
        page.category = body.category or "general"
        page.heading = body.heading
        page.keywords = body.keywords or ""
        page.word_count = body.word_count or 0
        page.status = body.status or "published"
        if body.status == "published":
            page.published_at = now
        page.updated_at = now
        await db.commit()
        logger.info(f"Admin {current_user.id} updated SEO page: {body.slug}")
        return {"success": True, "message": f"页面 '{body.slug}' 已更新",
                "data": {"slug": page.slug, "status": page.status}}

    page = SeoPage(
        slug=body.slug,
        title=body.title,
        meta_description=body.meta_description or "",
        meta_keywords=body.meta_keywords or "",
        content_html=body.content_html,
        structured_data=body.structured_data,
        category=body.category or "general",
        heading=body.heading,
        keywords=body.keywords or "",
        status=body.status or "published",
        published_at=now if body.status == "published" else None,
        word_count=body.word_count or 0,
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    logger.info(f"Admin {current_user.id} created SEO page: {body.slug}")
    return {"success": True, "message": f"页面 '{body.slug}' 已创建",
            "data": {"slug": page.slug, "status": page.status}}


# ---------------------------------------------------------------------------
# POST /pages/batch-import - 批量导入 SEO 页面 (admin only)
# ---------------------------------------------------------------------------

@router.post("/pages/batch-import", summary="批量导入 SEO 页面 (管理员)")
async def batch_import_seo_pages(
    body: SeoPageBatchImport,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """批量创建或更新 SEO 页面"""
    created = 0
    updated = 0
    failed = []
    now = datetime.utcnow()

    for item in body.pages:
        try:
            # 逐项跑闸门：不通过的项记入 failed 并跳过，不中断整批。
            target_status = item.status or "published"
            if target_status == "published":
                gate = run_quality_gate(item.content_html, slug=item.slug)
                if not gate.passed:
                    failed.append({
                        "slug": item.slug,
                        "error": "quality_gate_blocked",
                        "score": gate.score,
                        "critical_issues": list(gate.critical_issues),
                    })
                    logger.warning(
                        f"Admin {current_user.id} batch import BLOCKED "
                        f"'{item.slug}': score={gate.score}"
                    )
                    continue

            result = await db.execute(
                select(SeoPage).where(SeoPage.slug == item.slug)
            )
            page = result.scalar_one_or_none()

            if page:
                page.title = item.title
                page.meta_description = item.meta_description or ""
                page.meta_keywords = item.meta_keywords or ""
                page.content_html = item.content_html
                page.structured_data = item.structured_data
                page.category = item.category or "general"
                page.heading = item.heading
                page.keywords = item.keywords or ""
                page.word_count = item.word_count or 0
                page.status = item.status or "published"
                if item.status == "published":
                    page.published_at = now
                page.updated_at = now
                updated += 1
            else:
                page = SeoPage(
                    slug=item.slug,
                    title=item.title,
                    meta_description=item.meta_description or "",
                    meta_keywords=item.meta_keywords or "",
                    content_html=item.content_html,
                    structured_data=item.structured_data,
                    category=item.category or "general",
                    heading=item.heading,
                    keywords=item.keywords or "",
                    status=item.status or "published",
                    published_at=now if item.status == "published" else None,
                    word_count=item.word_count or 0,
                )
                db.add(page)
                created += 1
        except Exception as e:
            failed.append({"slug": item.slug, "error": str(e)})
            logger.error(f"Failed to import SEO page {item.slug}: {e}")

    await db.commit()
    logger.info(
        f"Admin {current_user.id} batch imported: "
        f"{created} created, {updated} updated, {len(failed)} failed"
    )
    return {"success": True,
            "message": f"批量导入完成: {created} 创建, {updated} 更新, {len(failed)} 失败",
            "data": {"created": created, "updated": updated, "failed": failed}}
