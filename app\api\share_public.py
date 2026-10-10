"""公开分享报告页面 - 带社交卡片元数据的HTML页面
任何人都可以通过分享链接查看报告摘要，无需登录
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.services.share_report_service import get_shared_report, increment_share_count
from app.config import settings

router = APIRouter(tags=["公开分享"])


@router.get("/share/report/{share_token}")
async def public_share_report(
    share_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """公开访问的健康报告分享页面

    返回带 OG tags 社交卡片元数据的 HTML 页面，
    支持微信、Twitter/Facebook 等平台的卡片预览。
    """
    report = await get_shared_report(db, share_token, increment_view=True)

    if not report:
        # 返回404页面
        html_content = _render_404_page()
        return HTMLResponse(content=html_content, status_code=404)

    # 取报告主人的有效邀请码，用于分享页 CTA 的推荐注册链接（获客闭环）
    ref_code = None
    try:
        from app.models.referral import InviteCode
        ic_res = await db.execute(
            select(InviteCode).where(
                InviteCode.inviter_id == str(report.user_id),
                InviteCode.status == "active",
            ).limit(1)
        )
        ic = ic_res.scalar_one_or_none()
        if ic:
            ref_code = ic.code
    except Exception:
        ref_code = None

    # 渲染分享页面
    html_content = _render_share_page(report, request, ref_code=ref_code)

    return HTMLResponse(content=html_content)


def _render_share_page(report, request, ref_code=None) -> str:
    """渲染分享报告HTML页面"""
    data = report.report_data or {}
    analysis = data.get("analysis_summary", {})
    nickname = data.get("nickname", "健康用户")
    health_score = report.health_score
    risk_level = report.risk_level or "low"

    # 分享页 CTA：带推荐码注册，形成获客闭环
    register_url = f"/register?ref={ref_code}" if ref_code else "/register"

    # 风险等级颜色
    risk_colors = {
        "low": "#22c55e",
        "medium": "#f59e0b",
        "high": "#ef4444",
    }
    risk_labels = {
        "low": "低风险",
        "medium": "中风险",
        "high": "高风险",
    }
    risk_color = risk_colors.get(risk_level, "#22c55e")
    risk_label = risk_labels.get(risk_level, "未知")

    # OG image: 使用 SVG 数据 URL 作为分享卡片图片（纯文本SVG）
    og_image = _generate_og_image_svg(nickname, health_score, risk_label)

    # 分享URL
    share_url = str(request.url)

    # 推荐列表
    recommendations = analysis.get("recommendations", [])
    rec_html = ""
    for rec in recommendations[:3]:
        rec_html += f'<li class="rec-item">{_escape_html(rec)}</li>'

    # 风险因素
    risk_factors = analysis.get("risk_factors", [])
    risk_html = ""
    for rf in risk_factors[:5]:
        risk_html += f'<span class="risk-tag">{_escape_html(rf)}</span>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(report.og_title or report.title)}</title>
    <meta name="description" content="{_escape_html(report.og_description or report.summary_text or '')}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="article">
    <meta property="og:url" content="{share_url}">
    <meta property="og:title" content="{_escape_html(report.og_title or report.title)}">
    <meta property="og:description" content="{_escape_html(report.og_description or report.summary_text or '')}">
    <meta property="og:image" content="{og_image}">
    <meta property="og:site_name" content="HealthLens">
    <meta property="og:locale" content="zh_CN">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:url" content="{share_url}">
    <meta name="twitter:title" content="{_escape_html(report.og_title or report.title)}">
    <meta name="twitter:description" content="{_escape_html(report.og_description or report.summary_text or '')}">
    <meta name="twitter:image" content="{og_image}">

    <!-- 微信分享优化 -->
    <meta name="share-title" content="{_escape_html(report.og_title or report.title)}">
    <meta name="share-description" content="{_escape_html(report.og_description or report.summary_text or '')}">
    <meta name="share-image" content="{og_image}">

    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 480px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .avatar {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea, #764ba2);
            margin: 0 auto 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 32px;
            font-weight: bold;
        }}
        .name {{
            font-size: 22px;
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 4px;
        }}
        .subtitle {{
            font-size: 14px;
            color: #94a3b8;
        }}
        .score-section {{
            text-align: center;
            padding: 24px;
            background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
            border-radius: 16px;
            margin-bottom: 24px;
        }}
        .score-label {{
            font-size: 14px;
            color: #64748b;
            margin-bottom: 8px;
        }}
        .score-value {{
            font-size: 56px;
            font-weight: 800;
            color: {risk_color};
            line-height: 1;
            margin-bottom: 8px;
        }}
        .score-unit {{
            font-size: 20px;
            color: #94a3b8;
        }}
        .risk-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            background: {risk_color};
            color: white;
        }}
        .stats {{
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-item {{
            flex: 1;
            text-align: center;
            padding: 16px;
            background: #f8fafc;
            border-radius: 12px;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: 700;
            color: #1a1a2e;
        }}
        .stat-label {{
            font-size: 12px;
            color: #94a3b8;
            margin-top: 4px;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #1a1a2e;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .section-title::before {{
            content: "";
            width: 4px;
            height: 16px;
            background: linear-gradient(180deg, #667eea, #764ba2);
            border-radius: 2px;
        }}
        .risk-tags {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .risk-tag {{
            padding: 4px 10px;
            background: #fef3c7;
            color: #b45309;
            border-radius: 6px;
            font-size: 12px;
        }}
        .rec-list {{
            list-style: none;
        }}
        .rec-item {{
            padding: 10px 12px;
            background: #f0fdf4;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 13px;
            color: #166534;
            padding-left: 28px;
            position: relative;
        }}
        .rec-item::before {{
            content: "✓";
            position: absolute;
            left: 10px;
            color: #22c55e;
            font-weight: bold;
        }}
        .cta {{
            margin-top: 24px;
            text-align: center;
        }}
        .cta-btn {{
            display: inline-block;
            padding: 14px 32px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            text-decoration: none;
            border-radius: 12px;
            font-weight: 600;
            font-size: 16px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .cta-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
        }}
        .footer {{
            margin-top: 20px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
        }}
        .view-count {{
            margin-top: 8px;
            font-size: 12px;
            color: #cbd5e1;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <div class="avatar">{nickname[0] if nickname else "H"}</div>
            <div class="name">{_escape_html(nickname)}</div>
            <div class="subtitle">HealthLens 健康报告</div>
        </div>

        <div class="score-section">
            <div class="score-label">健康评分</div>
            <div class="score-value">
                {health_score if health_score is not None else "--"}
                <span class="score-unit">/100</span>
            </div>
            <span class="risk-badge">{risk_label}</span>
        </div>

        <div class="stats">
            <div class="stat-item">
                <div class="stat-value">{analysis.get("total_items", 0)}</div>
                <div class="stat-label">监测指标</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" style="color: {risk_color}">{analysis.get("abnormal_count", 0)}</div>
                <div class="stat-label">异常项</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{len(risk_factors)}</div>
                <div class="stat-label">风险因素</div>
            </div>
        </div>

        {"<div class='section'><div class='section-title'>健康建议</div><ul class='rec-list'>" + rec_html + "</ul></div>" if recommendations else ""}

        {"<div class='section'><div class='section-title'>风险因素</div><div class='risk-tags'>" + risk_html + "</div></div>" if risk_factors else ""}

        <div class="cta">
            <a href="{register_url}" class="cta-btn">免费注册，生成你的专属健康报告</a>
        </div>

        <div class="footer">
            基于 HealthLens 健康分析系统生成
            <div class="view-count">已有 {report.view_count} 人查看</div>
        </div>
    </div>
</body>
</html>"""
    return html


def _render_404_page() -> str:
    """渲染404页面"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>报告不存在 | HealthLens</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 20px;
        }
        .card {
            background: white;
            border-radius: 20px;
            padding: 48px;
            max-width: 400px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .icon { font-size: 64px; margin-bottom: 16px; }
        h1 { color: #1a1a2e; margin-bottom: 8px; font-size: 24px; }
        p { color: #94a3b8; margin-bottom: 24px; }
        .btn {
            display: inline-block;
            padding: 12px 28px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            text-decoration: none;
            border-radius: 12px;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🔍</div>
        <h1>报告不存在</h1>
        <p>该分享链接可能已过期或被撤销</p>
        <a href="/" class="btn">返回首页</a>
    </div>
</body>
</html>"""


def _generate_og_image_svg(name: str, score: int | None, risk: str) -> str:
    """生成 SVG 格式的 OG 分享图片（使用 data URL）"""
    score_text = f"{score}" if score is not None else "--"
    name_text = name or "健康用户"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#667eea"/>
      <stop offset="100%" style="stop-color:#764ba2"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="100" y="90" width="1000" height="450" rx="24" fill="white" fill-opacity="0.95"/>
  <text x="600" y="200" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="48" font-weight="bold" fill="#1a1a2e" text-anchor="middle">{name_text}的健康报告</text>
  <text x="600" y="340" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="120" font-weight="800" fill="#22c55e" text-anchor="middle">{score_text}<tspan font-size="36" fill="#94a3b8">/100</tspan></text>
  <text x="600" y="420" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" fill="#64748b" text-anchor="middle">健康评分 · {risk}</text>
  <text x="600" y="500" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" fill="#94a3b8" text-anchor="middle">HealthLens · 基于你独特生物学特征的健康改善量化追踪系统</text>
</svg>'''

    import base64
    svg_b64 = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f"data:image/svg+xml;base64,{svg_b64}"


def _escape_html(text: str) -> str:
    """HTML转义"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
