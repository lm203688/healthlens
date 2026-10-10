"""SEO 公开页面路由
Mounted at /knowledge/, /health/, /health-tools/ and root for sitemap/robots
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response, HTMLResponse, PlainTextResponse
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.seo import SeoPage
from app.config import settings

# 统一主域（可通过环境变量 PUBLIC_BASE_URL 覆盖，默认 https://healthlens.cc）
SITE_BASE = settings.PUBLIC_BASE_URL


# ============================================================================
# HTML 页面模板
# ============================================================================

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HealthLens {title_suffix}</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{meta_keywords}">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:locale" content="{og_locale}">
    <meta property="og:site_name" content="HealthLens">
    <link rel="canonical" href="{canonical_url}">
{hreflang_tags}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; color: #1a1a2e; line-height: 1.8; background: #fafbfc; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 60px 20px; text-align: center; margin-bottom: 40px; }}
        header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        header p {{ opacity: 0.9; font-size: 1.1em; }}
        .content {{ background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 40px; }}
        .content h2 {{ color: #667eea; margin: 30px 0 15px; font-size: 1.5em; }}
        .content h3 {{ color: #764ba2; margin: 25px 0 12px; font-size: 1.2em; }}
        .content p {{ margin-bottom: 16px; color: #444; }}
        .content ul, .content ol {{ margin: 15px 0; padding-left: 25px; color: #444; }}
        .content li {{ margin-bottom: 8px; }}
        .content a {{ color: #667eea; text-decoration: none; }}
        .content a:hover {{ text-decoration: underline; }}
        .cta-float {{ position: fixed; bottom: 30px; right: 30px; z-index: 9999; }}
        .cta-btn {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; border-radius: 50px; text-decoration: none; font-weight: 600; font-size: 16px; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4); transition: transform 0.2s, box-shadow 0.2s; }}
        .cta-btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 25px rgba(102, 126, 234, 0.5); }}
        footer {{ text-align: center; padding: 30px 20px; color: #999; font-size: 0.9em; border-top: 1px solid #eee; }}
        footer a {{ color: #667eea; text-decoration: none; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <p>{header_tagline}</p>
    </header>
    <div class="container">
        <article class="content">
            {content_html}
        </article>
    </div>
    <div class="cta-float">
        <a href="{site_base}/register" class="cta-btn">Try HealthLens Free</a>
    </div>
    <footer>
        <p>&copy; {year} HealthLens. All rights reserved.</p>
        <p><a href="{site_base}/register">{footer_register}</a> | <a href="{site_base}">{footer_home}</a></p>
    </footer>
</body>
</html>"""


_TOOLS_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - HealthLens {title_suffix}</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{meta_keywords}">
    <meta name="robots" content="index, follow">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:locale" content="{og_locale}">
    <meta property="og:site_name" content="HealthLens">
    <link rel="canonical" href="{canonical_url}">
{hreflang_tags}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; color: #1a1a2e; line-height: 1.8; background: #fafbfc; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
        header {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 60px 20px; text-align: center; margin-bottom: 40px; }}
        header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        header p {{ opacity: 0.9; font-size: 1.1em; }}
        .content {{ background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 40px; }}
        .content h2 {{ color: #11998e; margin: 30px 0 15px; }}
        .content p {{ margin-bottom: 16px; color: #444; }}
        .cta-float {{ position: fixed; bottom: 30px; right: 30px; z-index: 9999; }}
        .cta-btn {{ display: inline-block; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 14px 28px; border-radius: 50px; text-decoration: none; font-weight: 600; font-size: 16px; box-shadow: 0 4px 20px rgba(17, 153, 142, 0.4); transition: transform 0.2s, box-shadow 0.2s; }}
        .cta-btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 25px rgba(17, 153, 142, 0.5); }}
        footer {{ text-align: center; padding: 30px 20px; color: #999; font-size: 0.9em; border-top: 1px solid #eee; }}
        footer a {{ color: #11998e; text-decoration: none; }}
    </style>
</head>
<body>
    <header>
        <h1>{title}</h1>
        <p>{header_tagline}</p>
    </header>
    <div class="container">
        <article class="content">
            {content_html}
        </article>
    </div>
    <div class="cta-float">
        <a href="{site_base}/register" class="cta-btn">Try HealthLens Free</a>
    </div>
    <footer>
        <p>&copy; {year} HealthLens. All rights reserved.</p>
        <p><a href="{site_base}/register">{footer_register}</a> | <a href="{site_base}">{footer_home}</a></p>
    </footer>
</body>
</html>"""


# ============================================================================
# 内部渲染函数
# ============================================================================

# 各语言的页面文案（模板占位符取值）
_LANG_CHROME = {
    "zh-CN": {
        "title_suffix": "健康知识",
        "tools_title_suffix": "免费健康工具",
        "header_tagline_article": "HealthLens - AI 驱动的健康全景平台",
        "header_tagline_tools": "免费在线健康计算工具 - HealthLens",
        "footer_register": "免费注册",
        "footer_home": "回到首页",
        "og_locale": "zh_CN",
        "not_found": "页面未找到",
        "back_home": "返回首页",
    },
    "en": {
        "title_suffix": "Health Knowledge",
        "tools_title_suffix": "Free Health Tools",
        "header_tagline_article": "HealthLens — AI-powered health platform",
        "header_tagline_tools": "Free online health calculators — HealthLens",
        "footer_register": "Sign up free",
        "footer_home": "Home",
        "og_locale": "en_US",
        "not_found": "Page not found",
        "back_home": "Back to home",
    },
}


def _not_found_html(lang: str) -> str:
    chrome = _LANG_CHROME.get(lang, _LANG_CHROME["zh-CN"])
    return f"""<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="UTF-8"><title>404 - HealthLens</title></head>
<body><h1>404</h1><p>{chrome['not_found']}</p>
<p><a href="{SITE_BASE}">{chrome['back_home']}</a></p></body></html>"""


def _en_payload(page: SeoPage) -> dict | None:
    """取页面的英文版本。无英文译本时返回 None —— 绝不回退成中文冒充英文。"""
    sd = page.structured_data or {}
    if not isinstance(sd, dict):
        return None
    i18n = sd.get("i18n") or {}
    if not isinstance(i18n, dict):
        return None
    en = i18n.get("en")
    if not isinstance(en, dict):
        return None
    if not (en.get("title") or "").strip():
        return None
    return en


def _hreflang_tags(url_prefix: str, slug: str, page: SeoPage, lang: str) -> str:
    """按实际存在的译本生成 hreflang —— 只为真实存在的语言页输出 alternate。"""
    zh_url = f"{SITE_BASE}{url_prefix}{slug}"
    has_en = _en_payload(page) is not None
    lines = []
    if has_en:
        en_url = f"{SITE_BASE}/en{url_prefix}{slug}"
        lines.append(f'    <link rel="alternate" hreflang="zh-CN" href="{zh_url}">')
        lines.append(f'    <link rel="alternate" hreflang="en" href="{en_url}">')
        lines.append(f'    <link rel="alternate" hreflang="x-default" href="{zh_url}">')
    return "\n".join(lines)


async def _render_seo_page(
    db: AsyncSession, slug: str, url_prefix: str, lang: str = "zh-CN"
) -> Response:
    """查询并渲染 SEO 页面为完整 HTML。

    lang="en" 时只渲染真实存在英文译本的页面；没有译本一律 404，
    避免产出「英文 URL 显示中文内容」的软 404。
    """
    result = await db.execute(
        select(SeoPage).where(
            SeoPage.slug == slug,
            SeoPage.status == "published",
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        return HTMLResponse(content=_not_found_html(lang), status_code=404)

    en = _en_payload(page) if lang == "en" else None
    if lang == "en" and en is None:
        return HTMLResponse(content=_not_found_html(lang), status_code=404)

    chrome = _LANG_CHROME.get(lang, _LANG_CHROME["zh-CN"])

    # 完整 HTML 直通模式：如果 content_html 是完整页面，直接输出（仅中文原文适用）
    content = page.content_html or ""
    stripped = content.strip().lower()
    if stripped.startswith("<!doctype html>") or stripped.startswith("<html"):
        if lang == "en":
            # 直通页没有英文译本，不能冒充英文
            return HTMLResponse(content=_not_found_html(lang), status_code=404)
        return HTMLResponse(
            content=content,
            status_code=200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "public, max-age=3600",
            },
        )

    # 选择模板: health-tools 用工具模板，其余用知识模板
    is_tools = url_prefix == "/health-tools/"
    template = _TOOLS_PAGE_TEMPLATE if is_tools else _PAGE_TEMPLATE

    if lang == "en":
        title = en.get("title") or slug
        meta_description = en.get("meta_description") or ""
        meta_keywords = en.get("meta_keywords") or page.meta_keywords or ""
        body = en.get("content_html") or f"<p>{title}</p>"
    else:
        title = page.title or slug
        meta_description = page.meta_description or ""
        meta_keywords = page.meta_keywords or ""
        body = page.content_html or f"<p>{page.title}</p>"

    canonical_url = f"{SITE_BASE}{'/en' if lang == 'en' else ''}{url_prefix}{slug}"
    html = template.format(
        title=title,
        meta_description=meta_description,
        meta_keywords=meta_keywords,
        canonical_url=canonical_url,
        content_html=body,
        site_base=SITE_BASE,
        year=datetime.utcnow().year,
        lang=lang,
        og_locale=chrome["og_locale"],
        title_suffix=chrome["tools_title_suffix"] if is_tools else chrome["title_suffix"],
        header_tagline=chrome["header_tagline_tools"] if is_tools else chrome["header_tagline_article"],
        footer_register=chrome["footer_register"],
        footer_home=chrome["footer_home"],
        hreflang_tags=_hreflang_tags(url_prefix, slug, page, lang),
    )

    return HTMLResponse(
        content=html,
        status_code=200,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
        },
    )

# ============================================================================
# 页面路由 - 挂载到 /knowledge/, /health/, /health-tools/
# ============================================================================

# GET /knowledge/{slug}
seo_knowledge_router = APIRouter()

@seo_knowledge_router.get("/{slug}", summary="SEO 知识页面")
async def serve_knowledge_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """以完整 HTML 返回 SEO 优化的知识页面，供搜索引擎抓取"""
    return await _render_seo_page(db, slug, "/knowledge/")


# GET /health/{slug}
health_router = APIRouter()

@health_router.get("/{slug}", summary="SEO 健康话题页面")
async def serve_health_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """健康话题的替代 URL 模式"""
    return await _render_seo_page(db, slug, "/health/")


# GET /health-tools/{slug}
health_tools_router = APIRouter()

@health_tools_router.get("/{slug}", summary="SEO 健康工具页面")
async def serve_health_tools_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """免费健康计算器/工具页面"""
    return await _render_seo_page(db, slug, "/health-tools/")


# ============================================================================
# 英文路由 - 挂载到 /en/knowledge/, /en/health/, /en/health-tools/
# 只有存在英文译本的页面才返回 200，其余 404（不产出软 404）
# ============================================================================

en_knowledge_router = APIRouter()

@en_knowledge_router.get("/{slug}", summary="SEO 知识页面（英文）")
async def serve_knowledge_page_en(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    return await _render_seo_page(db, slug, "/knowledge/", lang="en")


en_health_router = APIRouter()

@en_health_router.get("/{slug}", summary="SEO 健康话题页面（英文）")
async def serve_health_page_en(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    return await _render_seo_page(db, slug, "/health/", lang="en")


en_health_tools_router = APIRouter()

@en_health_tools_router.get("/{slug}", summary="SEO 健康工具页面（英文）")
async def serve_health_tools_page_en(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    return await _render_seo_page(db, slug, "/health-tools/", lang="en")

# 注意: sitemap.xml / robots.txt / llms.txt / ai.txt 已迁移至 geo_infra.py
