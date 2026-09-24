"""GEO (Generative Engine Optimization) 基础设施端点
基于 2026 GEO 最佳实践，为 AI 搜索引擎提供结构化指引文件。
整合 sitemap.xml 和 robots.txt，覆盖知识页面 + 免费工具页面。
"""
from datetime import datetime
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.seo import SeoPage
from app.config import settings

logger = logging.getLogger(__name__)

# 统一主域（可通过环境变量 PUBLIC_BASE_URL 覆盖，默认 https://healthlens.cc）
GEO_BASE = settings.PUBLIC_BASE_URL

geo_router = APIRouter()

# ============================================================================
# 静态文本内容
# ============================================================================

_LLMSTXT = """\
# HealthLens
> AI 健康分析平台 - 基于独特生物学特征的健康改善量化追踪系统

## About
HealthLens 是一个 AI 驱动的个人健康分析平台，提供体质分析、睡眠修复追踪、药食同源调理方案、基因组解读等健康改善量化追踪服务。

## Key Pages
- 知识库: https://healthlens.app/knowledge/
- BMI计算器: https://healthlens.app/health-tools/tools/bmi-calculator
- 睡眠评分: https://healthlens.app/health-tools/tools/sleep-score-calculator
- 中医体质自测: https://healthlens.app/health-tools/tools/tcm-constitution-test
- 药食同源查询: https://healthlens.app/health-tools/tools/food-medicine-query

## API Documentation
- API Docs: https://healthlens.app/docs

## For AI Assistants
- HealthLens 提供基于中医古籍知识库和现代生物学数据的健康分析服务
- 核心价值：量化追踪健康改善效果（修复评分、修复年龄）
- 所有建议基于药食同源理念，非药物治疗
- 用户隐私数据由用户完全拥有

## Structured Data
- Schema.org FAQPage, Article, HowTo, MedicalWebPage, WebApplication
- Sitemap: https://healthlens.app/sitemap.xml
"""

_AITXT = """\
# HealthLens
HealthLens: AI健康分析平台 | 药食同源 | 睡眠修复 | 体质量化追踪
域名: healthlens.app
功能: 体质分析、睡眠质量评分、中医体质自测、药食同源方案、基因组解读、修复评分追踪
内容: /knowledge/ (1000+ 健康知识页) | /health-tools/ (免费计算器)
特色: 基于中医古籍+生物学数据，非药物治疗，隐私优先
"""

_HUMANSTXT = """\
/* TEAM */
Project Lead: HealthLens Team
Backend: FastAPI + PostgreSQL + Redis
Frontend: Vue.js

/* SITE */
Last update: 2026/07/25
Standards: HTML5, CSS3, REST API (OpenAPI 3.0)
Language: Chinese (zh-CN) / English

/* THANKS */
Traditional Chinese Medicine Classics (中医古籍)
Open Source Community

/* ABOUT */
HealthLens - AI 驱动的个人健康分析平台
提供体质分析、睡眠修复追踪、药食同源调理方案、基因组解读等健康改善量化追踪服务。
Privacy-first, non-pharmacological approach based on 药食同源 philosophy.
"""

_ROBOTSTXT = """\
User-agent: *
Allow: /
Allow: /knowledge/
Allow: /health-tools/
Allow: /health/

# AI Engine Crawlers
User-agent: GPTBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: Claude-Web
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Applebot-Extended
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Bytespider
Allow: /
User-agent: Sogou web spider
Allow: /
User-agent: Baiduspider
Allow: /
User-agent: bingbot
Allow: /

Sitemap: https://healthlens.app/sitemap.xml
"""

# 免费工具页面（固定列表）
_TOOL_PAGES = [
    {"loc": "https://healthlens.app/health-tools/tools/bmi-calculator", "priority": "0.9", "changefreq": "monthly"},
    {"loc": "https://healthlens.app/health-tools/tools/sleep-score-calculator", "priority": "0.9", "changefreq": "monthly"},
    {"loc": "https://healthlens.app/health-tools/tools/tcm-constitution-test", "priority": "0.9", "changefreq": "monthly"},
    {"loc": "https://healthlens.app/health-tools/tools/food-medicine-query", "priority": "0.8", "changefreq": "weekly"},
]

# ============================================================================
# 缓存头
# ============================================================================

_GEO_CACHE = {"Cache-Control": "public, max-age=86400"}
_SITEMAP_CACHE = {"Cache-Control": "public, max-age=86400"}

# ============================================================================
# GEO 端点
# ============================================================================

@geo_router.get("/llms.txt", summary="AI 引擎指令文件")
async def llms_txt():
    return PlainTextResponse(content=_LLMSTXT.replace("https://healthlens.app", GEO_BASE), headers=_GEO_CACHE)


@geo_router.get("/llms-en.txt", summary="AI 引擎指令文件（英文）")
async def llms_en_txt():
    try:
        from pathlib import Path
        en_path = Path(__file__).parent / "llms_en.txt"
        if en_path.exists():
            content = en_path.read_text(encoding="utf-8")
            return PlainTextResponse(content=content.replace("https://healthlens.app", GEO_BASE), headers=_GEO_CACHE)
    except Exception:
        pass
    return PlainTextResponse(content=_LLMSTXT.replace("https://healthlens.app", GEO_BASE), headers=_GEO_CACHE)


@geo_router.get("/ai.txt", summary="AI 可读摘要")
async def ai_txt(db: AsyncSession = Depends(get_db)):
    # 动态反映真实知识页数量，避免对外宣称虚假的「1000+」
    try:
        from sqlalchemy import func
        count_res = await db.execute(
            select(func.count()).select_from(SeoPage).where(SeoPage.status == "published")
        )
        page_count = count_res.scalar() or 0
    except Exception:
        page_count = 0
    body = _AITXT.replace(
        "1000+ 健康知识页",
        f"{page_count} 个健康知识/工具页" if page_count else "健康知识页",
    ).replace("https://healthlens.app", GEO_BASE)
    return PlainTextResponse(content=body, headers=_GEO_CACHE)


@geo_router.get("/humans.txt", summary="项目信息")
async def humans_txt():
    return PlainTextResponse(content=_HUMANSTXT, headers=_GEO_CACHE)


@geo_router.get("/robots.txt", summary="GEO 优化版 robots.txt")
async def robots_txt():
    return PlainTextResponse(content=_ROBOTSTXT.replace("https://healthlens.app", GEO_BASE), headers=_GEO_CACHE)


@geo_router.get("/sitemap.xml", summary="动态 sitemap (知识页 + 工具页)")
async def sitemap_xml(db: AsyncSession = Depends(get_db)):
    """构建 sitemap：SEO 知识页面 + 免费工具页面

    hreflang alternates 只为**真实存在英文译本**的页面输出（判定依据
    SeoPage.structured_data.i18n.en 有非空 title）。绝不输出指向不存在
    页面的 alternate —— 软 404 会直接损害 SEO。
    """
    result = await db.execute(
        select(SeoPage).where(SeoPage.status == "published")
    )
    pages = result.scalars().all()

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]

    def _has_en(p: SeoPage) -> bool:
        sd = p.structured_data or {}
        if not isinstance(sd, dict):
            return False
        i18n = sd.get("i18n") or {}
        if not isinstance(i18n, dict):
            return False
        en = i18n.get("en")
        return bool(isinstance(en, dict) and (en.get("title") or "").strip())

    en_alternate_count = 0

    # 免费工具页面（高优先级）
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for tool in _TOOL_PAGES:
        loc = tool['loc'].replace('https://healthlens.app', GEO_BASE)
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{loc}</loc>")
        xml_lines.append(f"    <lastmod>{today}</lastmod>")
        xml_lines.append(f"    <changefreq>{tool['changefreq']}</changefreq>")
        xml_lines.append(f"    <priority>{tool['priority']}</priority>")
        xml_lines.append("  </url>")

    # SEO 知识页面（按 category 映射到正确的公开 URL 前缀）
    _PREFIX_BY_CATEGORY = {
        "health-tools": "/health-tools/",
        "tcm-constitution": "/health/",
        "tcm-symptom": "/health/",
    }
    for p in pages:
        prefix = _PREFIX_BY_CATEGORY.get(p.category, "/knowledge/")
        lastmod = (p.updated_at or p.created_at).strftime("%Y-%m-%d") if (p.updated_at or p.created_at) else today
        zh_url = f"{GEO_BASE}{prefix}{p.slug}"
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{zh_url}</loc>")
        if _has_en(p):
            en_url = f"{GEO_BASE}/en{prefix}{p.slug}"
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="zh-CN" href="{zh_url}"/>')
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="en" href="{en_url}"/>')
            xml_lines.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{zh_url}"/>')
            en_alternate_count += 1
        xml_lines.append(f"    <lastmod>{lastmod}</lastmod>")
        xml_lines.append("    <changefreq>weekly</changefreq>")
        xml_lines.append("    <priority>0.7</priority>")
        xml_lines.append("  </url>")

    xml_lines.append("</urlset>")
    logger.info(f"sitemap.xml: {len(pages)} pages, {en_alternate_count} with zh/en alternates")
    return Response(
        content="\n".join(xml_lines),
        media_type="application/xml",
        headers=_SITEMAP_CACHE,
    )
