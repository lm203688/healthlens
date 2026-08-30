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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paramiko

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

# 后端 sitemap 拉取（ECS 本机 FastAPI，含全部 SEO 长尾页，约 1255 条）
ECS_HOST = "150.158.119.19"
ECS_PORT = 22
ECS_USER = "ubuntu"
ECS_KEY = ROOT / ".workbuddy" / "cache" / "ecs_deploy_key"


def fetch_backend_sitemap() -> str | None:
    """从 ECS 本机 FastAPI 拉取真实 sitemap（/sitemap.xml，含后端 SEO 页 ~1255 条）。

    走 127.0.0.1:8000（nginx 反代源站），不经过 Cloudflare。失败返回 None 由调用方兜底。
    """
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            ECS_HOST, port=ECS_PORT, username=ECS_USER,
            key_filename=str(ECS_KEY), timeout=25,
            look_for_keys=False, allow_agent=False,
        )
        _, o, e = c.exec_command("curl -s -m20 http://127.0.0.1:8000/sitemap.xml")
        txt = o.read().decode(errors="ignore")
        c.close()
        if "<urlset" in txt and txt.count("<loc>") > 50:
            return txt
        log(f"  [WARN] 后端 sitemap 内容异常（<loc>={txt.count('<loc>')}），放弃使用")
    except Exception as ex:
        log(f"  [WARN] 后端 sitemap 拉取失败: {ex}")
    return None


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


def normalize_links(path: Path):
    """防御性收敛：无论源文件里出现什么外部域名（healthlens.com/app）或错路径（/education/），
    构建时一律强制收敛到本站 SITE_URL 与 /knowledge/ 路径，杜绝把权重/链接/结构化数据送给死域。
    """
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    CANON_RE = re.compile(r'(rel="canonical"\s+href=")([^"]*)(")', re.I)
    OGURL_RE = re.compile(r'(property="og:url"\s+content=")([^"]*)(")', re.I)

    def _fix(url: str) -> str:
        url = re.sub(r"^https?://[^/]+", SITE_URL, url, count=1)
        url = re.sub(r"/education/", "/knowledge/", url)
        return url

    new = CANON_RE.sub(lambda m: m.group(1) + _fix(m.group(2)) + m.group(3), txt)
    new = OGURL_RE.sub(lambda m: m.group(1) + _fix(m.group(2)) + m.group(3), new)
    # 全局收敛：正文中残留的外部域名 / 错路径也一并修正（含 JSON-LD、内部链接）
    new = re.sub(r"https?://healthlens\.app", SITE_URL, new)
    new = re.sub(r"https?://healthlens\.com", SITE_URL, new)
    new = re.sub(r"/education/", "/knowledge/", new)
    if new != txt:
        path.write_text(new, encoding="utf-8")


def build():
    started = datetime.now(CST)
    log("=" * 64)
    log("HealthLens 静态站点构建")
    log("=" * 64)

    # 禁止批量清空输出目录。
    # 此前是 shutil.rmtree(DIST)：dist 常见 60+ 文件，会触发本环境 safe-delete
    # 护栏（>50 文件/turn）使构建直接中止；且「先全删再重建」在任何环境都是
    # 高风险操作——构建中途失败会留下空站。现改为构建到一次性空目录，
    # 旧产物保留，由调用方显式清理。
    if DIST.exists() and any(DIST.iterdir()):
        log(f"[ERROR] 输出目录非空，中止构建以避免覆盖/批量删除: {DIST}")
        log("        请指定一个空目录，如: --out auto-pipeline/dist_build_20260829")
        log("=" * 64)
        return 1
    (DIST / "knowledge").mkdir(parents=True, exist_ok=True)

    errors = []

    # ---------- 1. 首页与静态资源 ----------
    log("\n[1/5] 首页与静态资源")
    idx = FRONTEND / "index.html"
    if idx.exists():
        shutil.copy2(idx, DIST / "index.html")
        normalize_links(DIST / "index.html")
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

    # ---------- 1b. Pages Functions / _worker.js（支付/接口 serverless 层） ----------
    functions_dir = FRONTEND / "functions"
    worker_file = FRONTEND / "_worker.js"
    if worker_file.is_file():
        # _worker.js 模式（Direct Upload 与 Git 模式均支持）：整合全部路由，
        # 不再复制分散的 functions/ 目录，避免两种模式冲突。
        log("  functions/            跳过（_worker.js 已整合全部路由，避免模式冲突）")
    elif functions_dir.is_dir():
        shutil.copytree(functions_dir, DIST / "functions", dirs_exist_ok=True)
        nf = len([f for f in (DIST / "functions").rglob("*") if f.is_file()])
        log(f"  functions/            {nf} 个 serverless 函数（支付/接口）")
    else:
        log("  [WARN] 无 functions 目录（支付接口将不可用）")

    # ---------- 1c. _worker.js（Pages 高级模式入口，整合全部路由，替代 functions 目录） ----------
    worker_src = FRONTEND / "_worker.js"
    if worker_src.is_file():
        shutil.copy2(worker_src, DIST / "_worker.js")
        log(f"  _worker.js            {worker_src.stat().st_size // 1024} KB（整合路由；Direct Upload 下替代 functions/ 使其真正运行）")
    else:
        log("  [WARN] 无 _worker.js（Direct Upload 模式 functions 不被编译，需改用 Git 构建或补 _worker.js）")

    # ---------- 1c-bis. React SPA 产品入口（frontend/ -> dist/app/） ----------
    # 根路径 / 保留给内容型 GEO 首页（SEO 主资产），SPA 挂载在 /app/ 子路径。
    # 对应 _worker.js 的第 3b 条路由（/app/** 回退到 /app/index.html）。
    spa_dist = ROOT / "frontend" / "dist"
    if spa_dist.is_dir() and (spa_dist / "index.html").is_file():
        shutil.copytree(spa_dist, DIST / "app", dirs_exist_ok=True)
        _files = [f for f in (DIST / "app").rglob("*") if f.is_file()]
        _size = sum(f.stat().st_size for f in _files)
        log(f"  app/                  {len(_files)} 个文件 / {_size // 1024} KB（React SPA，入口 /app/）")
    else:
        log(f"  [WARN] 无 React SPA 产物: {spa_dist}（/app/ 不可用；先在 frontend/ 跑 npm run build）")

    # ---------- 1d. 信任/法务静态页（隐私/条款/免责/安全/关于/联系/更新日志/帮助/API） ----------
    # 独立 HTML，由 _worker.js 的 serveStatic(path+".html") 直接命中 /privacy 等，不依赖 SPA。
    legal_slugs = ["privacy", "terms", "disclaimer", "security", "about", "contact", "changelog", "help", "api-docs"]
    legal_n = 0
    for slug in legal_slugs:
        src = FRONTEND / f"{slug}.html"
        if src.is_file():
            shutil.copy2(src, DIST / f"{slug}.html")
            normalize_links(DIST / f"{slug}.html")
            legal_n += 1
    if legal_n:
        log(f"  信任页                {legal_n} 个（/privacy /terms /disclaimer /security /about /contact /changelog /help /api-docs）")

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
        normalize_links(DIST / "knowledge" / name)
    log(f"  {'去重后合计':<28} {len(pages):>3} 页")
    for name, old, new in overridden:
        log(f"     覆盖: {name}  ({old} -> {new})")

    if not pages:
        errors.append("没有任何知识库页面，产物无内容价值")

    # ---------- 3. sitemap.xml ----------
    log("\n[3/5] sitemap.xml")
    metas = {}
    for name in pages:
        metas[name] = extract_meta(DIST / "knowledge" / name)
    today = started.strftime("%Y-%m-%d")
    backend_xml = fetch_backend_sitemap()
    if backend_xml:
        # 后端 sitemap 含全部 SEO 长尾页（tcm-herb / faq / symptom / constitution / health-tools）
        (DIST / "sitemap.xml").write_text(backend_xml, encoding="utf-8")
        sitemap_count = backend_xml.count("<loc>")
        log(f"  {sitemap_count} 条 URL（来自后端 FastAPI /sitemap.xml，含全部 SEO 长尾页）")
    else:
        # 兜底：仅本地知识库页面（后端不可达时）
        entries = [{"loc": f"{SITE_URL}/", "priority": "1.0", "changefreq": "weekly"}]
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
        sitemap_count = len(entries)
        log(f"  {sitemap_count} 条 URL（本地知识库兜底，未能连接后端）")

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

    # humans.txt（人类可读的项目/团队信息，GEO 文件之一）
    humans = (
        "# humans.txt - HealthLens\n\n"
        "/* TEAM */\n"
        f"Site: {SITE_URL}\n"
        "Maintainer: HealthLens Team\n"
        f"Contact: {SITE_URL}\n\n"
        "/* SITE */\n"
        "Language: zh-CN\n"
        "Doctype: HTML5\n"
        "Backend: FastAPI + PostgreSQL\n"
        "Frontend: Cloudflare Pages\n"
        f"Last update: {today}\n"
    )
    (DIST / "humans.txt").write_text(humans, encoding="utf-8")

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
    log("  robots.txt / llms.txt / ai.txt / _headers 已生成")

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
        "sitemap_urls": sitemap_count,
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
    log(f"  知识页面 : {len(pages)}    sitemap: {sitemap_count} 条")
    if errors:
        log(f"\n  构建失败，{len(errors)} 个问题:")
        for e in errors:
            log(f"    - {e}")
        log("=" * 64)
        return 1
    log("  构建成功，可直接部署到任意静态托管")
    log("=" * 64)
    return 0


def set_out_dir(p: Path) -> None:
    """切换输出目录（供命令行 --out 与自动一次性目录使用）。"""
    global DIST
    DIST = p


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="HealthLens 静态站点构建")
    ap.add_argument(
        "--out", default=None,
        help="输出目录。留空默认 auto-pipeline/dist；若其非空则自动改用一次性目录 dist_build_<ts>",
    )
    args = ap.parse_args()

    if args.out:
        set_out_dir(Path(args.out))
    elif DIST.exists() and any(DIST.iterdir()):
        # dist 已有产物时自动切到一次性目录：既不覆盖旧产物，也绕开批量删除。
        set_out_dir(PIPELINE / f"dist_build_{datetime.now(CST).strftime('%Y%m%d_%H%M%S')}")
        log(f"dist 非空，改用一次性输出目录: {DIST}")

    sys.exit(build())
