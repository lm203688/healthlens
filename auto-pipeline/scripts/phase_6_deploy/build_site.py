"""静态站点构建器 —— 把散落的内容资产打包成可直接托管的 dist/

为什么需要它：
    此前 deploy 阶段永久 dry_run，content/generated/ 是空目录，
    43 个已生成的 HTML 页面散落在 reports/ 下从未上线过。
    没有一个环节把"内容资产"变成"可部署产物"。

产物结构（Cloudflare Pages / GitHub Pages / 任意静态托管均可直接用）:
    dist/
      index.html          首页（单页应用，无需构建）
      assets/             js/css
      knowledge/*.html    知识库页面
      sitemap.xml         从真实文件生成，不是硬编码
      robots.txt          含 AI 爬虫白名单
      llms.txt            GEO 卡位：给大模型看的站点说明
      ai.txt              AI 抓取声明
      _headers            Cloudflare Pages 响应头

设计原则：
    - 只搬运真实存在的文件，不生成占位内容
    - 同名文件取最新批次（按目录日期），并在报告里说明被覆盖的版本
    - 构建失败必须非 0 退出（此前所有环节都是 fail-open）
"""
import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[3]          # .../healthlens
PIPELINE = ROOT / "auto-pipeline"
DIST = PIPELINE / "dist"

SITE_URL = "https://healthlens.cc"
SITE_NAME = "HealthLens"
SITE_DESC = "AI 驱动的精准健康平台：体检数据解读 → 细胞层面归因 → 中医食养修复方案"

# 内容来源，靠前的优先级低（会被靠后的同名文件覆盖）
CONTENT_SOURCES = [
    ROOT / "reports" / "seo-pages" / "batch-1-2026-07-24",
    ROOT / "reports" / "seo-pages" / "education-2026-07-24",
    ROOT / "reports" / "seo-pages" / "batch2-2026-07-25",
    ROOT / "reports" / "education" / "education-2026-07-31",
    PIPELINE / "content" / "generated",     # 流水线新产出，优先级最高
]

FRONTEND = ROOT / "healthlens" / "frontend"


def log(m=""):
    print(m, flush=True)


def extract_meta(html_path: Path) -> dict:
    """从 HTML 里抽 title / description，用于 sitemap 与 llms.txt"""
    try:
        txt = html_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    title = re.search(r"<title>(.*?)</title>", txt, re.S | re.I)
    desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', txt, re.S | re.I)
    return {
        "title": (title.group(1).strip() if title else html_path.stem),
        "description": (desc.group(1).strip() if desc else ""),
        "bytes": html_path.stat().st_size,
    }


def build():
    started = datetime.now(CST)
    log("=" * 64)
    log("HealthLens 静态站点构建")
    log("=" * 64)

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "knowledge").mkdir(parents=True, exist_ok=True)

    errors = []

    # ---------- 1. 首页与静态资源 ----------
    log("\n[1/5] 首页与静态资源")
    idx = FRONTEND / "index.html"
    if idx.exists():
        shutil.copy2(idx, DIST / "index.html")
        log(f"  index.html            {idx.stat().st_size // 1024} KB")
    else:
        errors.append(f"首页缺失: {idx}")
        log(f"  [FAIL] 首页缺失: {idx}")

    assets_dir = FRONTEND / "assets"
    if assets_dir.is_dir():
        shutil.copytree(assets_dir, DIST / "assets", dirs_exist_ok=True)
        n = len(list((DIST / "assets").rglob("*")))
        log(f"  assets/               {n} 个文件")
    else:
        log("  [WARN] 无 assets 目录")

    # ---------- 1b. Pages Functions（支付/接口 serverless 层） ----------
    # 记录函数数量到 manifest，方便线上核验（之前函数未进产物却无痕迹，难以排查）
    functions_count = 0
    functions_dir = FRONTEND / "functions"
    log(f"  [debug] functions_dir = {functions_dir}  exists={functions_dir.is_dir()}")
    if functions_dir.is_dir():
        shutil.copytree(functions_dir, DIST / "functions", dirs_exist_ok=True)
        functions_count = len([f for f in (DIST / "functions").rglob("*") if f.is_file()])
        log(f"  functions/            {functions_count} 个 serverless 函数（支付/接口）")
    else:
        # 兜底：在 ROOT 下全局搜索 functions 目录，避免路径假设失误导致漏复制
        hits = sorted({p.parent for p in ROOT.rglob("functions") if p.is_dir()})
        log(f"  [WARN] 未找到 {functions_dir}（支付接口将不可用）；候选 functions 目录: {[str(h) for h in hits]}")
        for h in hits:
            try:
                shutil.copytree(h, DIST / "functions", dirs_exist_ok=True)
                functions_count = len([f for f in (DIST / "functions").rglob("*") if f.is_file()])
                log(f"  [fallback] 已从 {h} 复制 {functions_count} 个函数")
                break
            except Exception as e:
                log(f"  [fallback][ERR] {h}: {e}")

    # ---------- 2. 知识库页面（去重，后者覆盖前者） ----------
    log("\n[2/5] 知识库页面")
    pages, overridden = {}, []
    for src in CONTENT_SOURCES:
        if not src.is_dir():
            continue
        found = sorted(src.glob("*.html"))
        for f in found:
            if f.name in pages:
                overridden.append((f.name, pages[f.name].parent.name, src.name))
            pages[f.name] = f
        # 批次自带的 assets 也要合并
        sub_assets = src / "assets"
        if sub_assets.is_dir():
            shutil.copytree(sub_assets, DIST / "assets", dirs_exist_ok=True)
        if found:
            log(f"  {src.name:<28} {len(found):>3} 页")

    for name, f in sorted(pages.items()):
        shutil.copy2(f, DIST / "knowledge" / name)
    log(f"  {'去重后合计':<28} {len(pages):>3} 页")
    for name, old, new in overridden:
        log(f"     覆盖: {name}  ({old} -> {new})")

    if not pages:
        # 知识页缺失只影响 SEO/GEO 覆盖，不应阻断前端与支付函数上线
        # （8-04 事故教训保留：站点身份 HealthLens 仍作为硬性校验）
        log("  [WARN] 无任何知识库页面（auto-pipeline 尚未生成），仍部署前端与函数")

    # ---------- 3. sitemap.xml ----------
    log("\n[3/5] sitemap.xml")
    entries = [{"loc": f"{SITE_URL}/", "priority": "1.0", "changefreq": "weekly"}]
    metas = {}
    for name in sorted(pages):
        p = DIST / "knowledge" / name
        metas[name] = extract_meta(p)
        entries.append({
            "loc": f"{SITE_URL}/knowledge/{name}",
            "priority": "0.8",
            "changefreq": "monthly",
        })
    today = started.strftime("%Y-%m-%d")
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries:
        xml += ["  <url>", f"    <loc>{e['loc']}</loc>", f"    <lastmod>{today}</lastmod>",
                f"    <changefreq>{e['changefreq']}</changefreq>",
                f"    <priority>{e['priority']}</priority>", "  </url>"]
    xml.append("</urlset>")
    (DIST / "sitemap.xml").write_text("\n".join(xml), encoding="utf-8")
    log(f"  {len(entries)} 条 URL（全部来自真实文件，无占位）")

    # ---------- 4. robots.txt / llms.txt / ai.txt ----------
    log("\n[4/5] GEO 文件（robots / llms / ai）")
    robots = f"""# {SITE_NAME} robots.txt
# 明确欢迎 AI 爬虫——内容分发的主要入口正在从搜索引擎转向大模型
User-agent: *
Allow: /

# 大模型抓取器白名单
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: anthropic-ai
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Bytespider
Allow: /
User-agent: Baiduspider
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    (DIST / "robots.txt").write_text(robots, encoding="utf-8")

    llms = [f"# {SITE_NAME}", "", f"> {SITE_DESC}", "",
            "## 这个站点是做什么的", "",
            "HealthLens 处理一条完整的因果链：体检指标异常 → 生化通路归因 →",
            "细胞层面机制 → 中医证候映射 → 药食同源的非药物干预方案。",
            "核心主张是：多数亚健康问题应先用饮食与作息干预，而非直接用药。", "",
            "## 内容索引", ""]
    for name in sorted(pages):
        m = metas.get(name, {})
        t = m.get("title", name).split("|")[0].strip()
        d = m.get("description", "")
        llms.append(f"- [{t}]({SITE_URL}/knowledge/{name})" + (f": {d[:110]}" if d else ""))
    llms += ["", "## 使用说明", "",
             "内容面向健康科普，不构成医疗建议。涉及疾病诊断与治疗请遵医嘱。",
             "药食同源方案在与处方药同用前需评估相互作用（例如当归与华法林同用会增加出血风险）。",
             "", f"最后更新: {today}"]
    (DIST / "llms.txt").write_text("\n".join(llms), encoding="utf-8")

    ai_txt = f"""# AI 抓取声明 - {SITE_NAME}
# 遵循 llmstxt.org 与 ai.txt 约定

Site: {SITE_URL}
Purpose: 健康科普与非药物养生方案
Training-Data: allowed
Attribution: required
Contact: {SITE_URL}
Structured-Index: {SITE_URL}/llms.txt
Sitemap: {SITE_URL}/sitemap.xml
Content-Type: 健康科普 / 中医食养 / 细胞机制解读
Medical-Disclaimer: 内容不构成诊疗建议
Last-Updated: {today}
"""
    (DIST / "ai.txt").write_text(ai_txt, encoding="utf-8")

    headers = """/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: SAMEORIGIN
  Referrer-Policy: strict-origin-when-cross-origin

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/knowledge/*
  Cache-Control: public, max-age=3600

/llms.txt
  Content-Type: text/plain; charset=utf-8
  Cache-Control: public, max-age=3600

/ai.txt
  Content-Type: text/plain; charset=utf-8
"""
    (DIST / "_headers").write_text(headers, encoding="utf-8")

    # 路由声明：把 /api/* 留给 Pages Functions，避免被 SPA 兜底成 index.html
    routes = {
        "version": 1,
        "include": ["/*"],
        "exclude": [
            "/api/*",
            "/assets/*",
            "/knowledge/*",
            "/build-manifest.json",
            "/sitemap.xml",
            "/robots.txt",
            "/llms.txt",
            "/ai.txt",
        ],
    }
    (DIST / "_routes.json").write_text(json.dumps(routes, ensure_ascii=False, indent=2), encoding="utf-8")
    log("  robots.txt / llms.txt / ai.txt / _headers / _routes.json 已生成")

    # ---------- 5. 构建校验 ----------
    log("\n[5/5] 构建产物校验")
    must_exist = ["index.html", "sitemap.xml", "robots.txt", "llms.txt", "ai.txt"]
    for f in must_exist:
        p = DIST / f
        ok = p.exists() and p.stat().st_size > 0
        if not ok:
            errors.append(f"产物缺失或为空: {f}")
        log(f"  {'[OK]  ' if ok else '[FAIL]'} {f:<16} {p.stat().st_size if p.exists() else 0} bytes")

    # 站点身份自检：产物里必须含 HealthLens 标识。
    # 这条是 8-04 事故的直接教训——部署目标曾指向别人的站点而无人发现。
    idx_txt = (DIST / "index.html").read_text(encoding="utf-8", errors="replace") if (DIST / "index.html").exists() else ""
    identity_ok = "HealthLens" in idx_txt
    if not identity_ok:
        errors.append("首页不含 HealthLens 标识，疑似内容来源错误")
    log(f"  {'[OK]  ' if identity_ok else '[FAIL]'} {'站点身份标识':<16} {'含 HealthLens' if identity_ok else '缺失'}")

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    count = len([f for f in DIST.rglob("*") if f.is_file()])

    manifest = {
        "built_at": started.isoformat(),
        "site_url": SITE_URL,
        "files": count,
        "total_bytes": total,
        "knowledge_pages": len(pages),
        "functions_count": functions_count,
        "sitemap_urls": len(entries),
        "sources": [str(s.relative_to(ROOT)) for s in CONTENT_SOURCES if s.is_dir()],
        "overridden": [{"file": n, "from": o, "to": t} for n, o, t in overridden],
        "errors": errors,
        "status": "success" if not errors else "failed",
    }
    (DIST / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    log("\n" + "=" * 64)
    log(f"  产物目录 : {DIST}")
    log(f"  文件总数 : {count}    体积: {total // 1024} KB")
    log(f"  知识页面 : {len(pages)}    sitemap: {len(entries)} 条")
    if errors:
        log(f"\n  构建失败，{len(errors)} 个问题:")
        for e in errors:
            log(f"    - {e}")
        log("=" * 64)
        return 1
    log("  构建成功，可直接部署到任意静态托管")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(build())
