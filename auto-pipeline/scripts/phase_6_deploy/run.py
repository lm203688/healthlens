"""
阶段6：部署上架（Cloudflare Pages）

真实发布通道
------------
HealthLens 前端是 Cloudflare Pages 静态站（healthlens.cc），_worker.js 把
/api、/knowledge 等路由代理到源站。知识页是 Pages 的静态资源，不是后端数据库
内容：后端 /knowledge/{slug} 只对数据库里已有的 slug 返回 200，其余 404，由
worker 回落到静态资源。

所以「部署」的真实含义是：
    build_site.py 构建静态产物  ->  wrangler pages deploy  ->  healthlens.cc 生效

本文件此前的实现（SCP 单文件上传到 ECS 的 /opt/healthlens/web/static/knowledge）
与真实架构完全不符：
  1. 该远程路径在服务器上根本不存在（实测 ls 报 No such file or directory）；
  2. deployment.dry_run 默认 True，且代码 .get("dry_run", True) 兜底，
     导致管线从未真正上线过任何内容；
  3. scp 命令不带 -i，用的是默认 ~/.ssh/id_*，本机的 ECS 部署密钥用不上。
结果就是「报告说部署成功，线上其实从未更新」这类假成功。

现已改为：真实构建 + 真实 CF Pages 部署 + 线上回读校验，并逐项标注是否真的
出现在构建产物里。

凭据
----
Cloudflare Pages 令牌放在 config.json 的 deployment.cf_tokens_file
（默认 .workbuddy/cache/cf_tokens.json，已 gitignore）。令牌会逐个尝试——
实测同一批令牌权限不一致（有的能列账户但不能动 healthlens 这个 Pages 项目，
报 10000），硬编码单个令牌会很脆。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import (  # noqa: E402
    start_phase, complete_phase, fail_phase,
    get_state, save_state, BASE_DIR, log
)

REPO_ROOT = BASE_DIR.parent
PHASE_DIR = Path(__file__).resolve().parent
BUILD_SCRIPT = PHASE_DIR / "build_site.py"
PAGES_DEPLOY = REPO_ROOT / "tools" / "cf_pages_deploy.py"

# build_site.py 需要 paramiko（用于从 ECS 拉后端 sitemap）。按顺序找可用解释器。
PY_EXE_CANDIDATES = [
    os.environ.get("HEALTHLENS_PYTHON", ""),
    "C:/Users/xing/.workbuddy/binaries/python/versions/3.13.12/python.exe",
    sys.executable,
]
NODE_EXE = os.environ.get(
    "NODE_EXE", "C:/Users/xing/.workbuddy/binaries/node/versions/22.22.2/node.exe"
)
DEFAULT_BASE_URL = "https://healthlens.cc"
IDENTITY_MARKERS = ["healthlens", "HealthLens"]
FORBIDDEN_MARKERS = ["aishield", "AIShield", "roboparts", "oraclemind"]


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _pick_python() -> str:
    """选一个装有 paramiko 的 python 解释器。"""
    for exe in PY_EXE_CANDIDATES:
        if not exe:
            continue
        try:
            r = subprocess.run(
                [exe, "-c", "import paramiko"],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0:
                return exe
        except Exception:
            continue
    raise RuntimeError(
        "找不到装有 paramiko 的 python 解释器，请设置 HEALTHLENS_PYTHON 环境变量"
    )


def _load_tokens(token_file: str) -> list[str]:
    """读取 CF Pages 令牌列表。支持 JSON 数组、{tokens: [...]} 或每行一个。"""
    if not token_file:
        raise RuntimeError("deployment.cf_tokens_file 未配置")
    p = (BASE_DIR.parent / token_file) if not os.path.isabs(token_file) else Path(token_file)
    if not p.is_file():
        raise RuntimeError(f"令牌文件不存在: {p}")
    txt = p.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(txt)
        if isinstance(data, dict):
            data = data.get("tokens") or data.get("token") or []
        if isinstance(data, list):
            return [str(t).strip() for t in data if str(t).strip()]
    except Exception:
        pass
    return [ln.strip() for ln in txt.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _http(url: str, timeout: int = 25) -> tuple[int, str]:
    """返回 (状态码, 响应体)。状态码 0 表示网络层失败。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "HealthLens-Pipeline/2.0",
            "Cache-Control": "no-cache",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(400000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            body = e.read(400000).decode("utf-8", "ignore")
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------
def build_dist(py_exe: str, out_dir: Path) -> bool:
    """构建静态产物到一次性空目录 out_dir。"""
    out_dir = out_dir.resolve()
    log(f"[build] 输出目录: {out_dir}")
    r = subprocess.run(
        [py_exe, str(BUILD_SCRIPT), "--out", str(out_dir)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )
    for line in (r.stdout or "").splitlines()[-24:]:
        log(f"  {line}")
    if r.returncode != 0:
        log(f"[build] 失败 (exit {r.returncode})\n{r.stderr[-800:]}", level="ERROR")
        return False
    n = sum(1 for _ in out_dir.rglob("*") if _.is_file())
    log(f"[build] OK -> {n} 个文件")
    return n > 0


# --------------------------------------------------------------------------
# 部署（CF Pages）
# --------------------------------------------------------------------------
def deploy_to_pages(dist_dir: Path, config: dict) -> dict:
    """部署到 Cloudflare Pages。逐令牌尝试，返回详情。"""
    d = config.get("deployment", {})
    account_id = (d.get("cf_account_id") or "").strip()
    project = d.get("pages_project") or "healthlens"
    if not account_id:
        return {"ok": False, "error": "deployment.cf_account_id 未配置"}
    if not Path(NODE_EXE).is_file():
        return {"ok": False, "error": f"找不到 node（cf_pages_deploy.py 内部需要它跑 wrangler）: {NODE_EXE}"}
    if not PAGES_DEPLOY.is_file():
        return {"ok": False, "error": f"找不到部署脚本: {PAGES_DEPLOY}"}

    try:
        py_exe = _pick_python()
        tokens = _load_tokens(d.get("cf_tokens_file", ""))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not tokens:
        return {"ok": False, "error": "令牌列表为空"}

    attempts = []
    for tok in tokens:
        env = os.environ.copy()
        env["CLOUDFLARE_API_TOKEN"] = tok
        env["CLOUDFLARE_ACCOUNT_ID"] = account_id
        # 注意：cf_pages_deploy.py 是 Python 脚本，必须用 python 调用；
        # 它内部自己再用 node 跑 wrangler。此前误用 node 执行 .py 文件，
        # 三个令牌全部 exit 1，正是这个原因。
        cmd = [
            py_exe, str(PAGES_DEPLOY),
            "--account-id", account_id,
            "--token", tok,
            "--project", project,
            "--dist", str(dist_dir),
            "--no-build",
        ]
        started = time.time()
        try:
            r = subprocess.run(
                cmd, cwd=str(REPO_ROOT), env=env,
                capture_output=True, text=True, timeout=900,
            )
            rc, out = r.returncode, (r.stdout or "")
        except Exception as e:
            rc, out = -1, f"{type(e).__name__}: {e}"

        entry = {
            "token_prefix": tok[:12] + "...",
            "returncode": rc,
            "seconds": round(time.time() - started, 1),
            "output_tail": out.strip().splitlines()[-6:],
        }
        attempts.append(entry)

        if rc == 0:
            # 从 wrangler 输出里抓预览地址，便于人工核对
            url = ""
            for line in out.splitlines():
                if "pages.dev" in line:
                    url = line.strip()
            log(f"[deploy] 成功（令牌 {entry['token_prefix']}，{entry['seconds']}s）")
            return {"ok": True, "token_prefix": entry["token_prefix"],
                    "preview": url, "attempts": attempts}
        log(f"[deploy] 令牌 {entry['token_prefix']} 失败 (exit {rc})，尝试下一个", level="WARN")

    return {"ok": False, "error": "全部令牌部署失败", "attempts": attempts}


# --------------------------------------------------------------------------
# 线上回读校验
# --------------------------------------------------------------------------
def verify_live(base_url: str, slugs: list[str]) -> list[dict]:
    """回读线上，确认每个 slug 真的能访问且内容是 HealthLens 自己的。"""
    ts = int(time.time())
    results = []
    for slug in slugs:
        url = f"{base_url}/knowledge/{slug}?{ts}"
        code, body = _http(url)
        low = body.lower()
        has_identity = any(m.lower() in low for m in IDENTITY_MARKERS)
        hit_forbidden = [m for m in FORBIDDEN_MARKERS if m.lower() in low]
        if code == 200 and has_identity and not hit_forbidden:
            status = "ok"
        elif code == 200 and not has_identity:
            status = "unrecognized_content"
        elif hit_forbidden:
            status = "wrong_site"
        elif code == 0:
            status = "network_error"
        else:
            status = f"http_{code}"
        results.append({
            "slug": slug,
            "http_code": code,
            "bytes": len(body),
            "status": status,
            "note": f"网络错误: {body[:120]}" if code == 0 else "",
        })
        log(f"  [verify] {slug}: HTTP {code} {status} ({len(body)} bytes)")
    return results


# --------------------------------------------------------------------------
# 主流程：把内容项映射到「构建产物里是否真的存在」
# --------------------------------------------------------------------------
def deploy_to_server(content_items, config):
    """部署内容上线，并逐项如实标注结果。"""
    d = config.get("deployment", {})
    results = []

    dry_run = bool(d.get("dry_run", True))
    if dry_run:
        log("部署模式: dry-run —— 不会真正构建/上线", level="WARN")
        for item in content_items:
            results.append({
                "task_id": item["task_id"],
                "file": item["content_file"],
                "status": "not_deployed",
                "mode": "dry-run",
                "note": "dry-run：未真正上线（deployment.dry_run=true）",
            })
        return results

    missing = [n for n, v in (("cf_account_id", d.get("cf_account_id")),
                              ("cf_tokens_file", d.get("cf_tokens_file"))) if not v]
    if missing:
        log(f"部署配置不完整(缺 {', '.join(missing)})，跳过真实部署", level="WARN")
        for item in content_items:
            results.append({
                "task_id": item["task_id"],
                "file": item["content_file"],
                "status": "not_deployed",
                "mode": f"配置不完整(缺 {', '.join(missing)})",
                "note": "未真正上线",
            })
        return results

    # 1. 构建到一次性目录
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BASE_DIR / f"dist_build_{ts}"
    try:
        py_exe = _pick_python()
    except Exception as e:
        log(f"解释器选择失败: {e}", level="ERROR")
        return [{"task_id": i["task_id"], "file": i["content_file"],
                 "status": "failed", "error": str(e)} for i in content_items]

    if not build_dist(py_exe, out_dir):
        return [{"task_id": i["task_id"], "file": i["content_file"],
                 "status": "failed", "error": "静态站点构建失败"} for i in content_items]

    # 2. 真实部署
    dep = deploy_to_pages(out_dir, config)
    if not dep.get("ok"):
        log(f"部署失败: {dep.get('error')}", level="ERROR")
        for item in content_items:
            results.append({
                "task_id": item["task_id"],
                "file": item["content_file"],
                "status": "failed",
                "error": dep.get("error", "部署失败"),
                "attempts": dep.get("attempts", []),
            })
        return results

    # 3. 逐项核对：产物里真的存在才算 deployed
    built = {p.name for p in (out_dir / "knowledge").glob("*.html")} if (out_dir / "knowledge").is_dir() else set()
    slugs = []
    for item in content_items:
        slug = Path(item["content_file"]).stem
        exists = slug in built or f"{slug}.html" in built
        results.append({
            "task_id": item["task_id"],
            "file": item["content_file"],
            "status": "deployed" if exists else "not_in_build",
            "slug": slug,
            "remote_path": f"/knowledge/{slug}.html",
            "preview": dep.get("preview", ""),
            "note": "" if exists else "该内容未出现在本次构建产物中（可能未通过上游阶段）",
        })
        if exists:
            slugs.append(slug)

    # 4. 线上回读校验（抽样，最多 12 个，避免拖慢管线）
    base_url = (d.get("site_url") or DEFAULT_BASE_URL).rstrip("/")
    verify_results = verify_live(base_url, slugs[:12]) if slugs else []
    bad = [v for v in verify_results if v["status"] != "ok"]
    for item in results:
        v = next((x for x in verify_results if x["slug"] == item["slug"]), None)
        if v:
            item["live_check"] = v
    if bad:
        log(f"[verify] {len(bad)}/{len(verify_results)} 个页面线上校验未通过", level="WARN")

    return results


def update_sitemap(new_items, config):
    """更新 sitemap.xml。

    仅收录真正 deployed 的条目。模拟/未上线的文件不应进 sitemap，
    否则会生成指向不存在页面的 URL。
    """
    base_url = (config.get("deployment", {}).get("site_url")
                or DEFAULT_BASE_URL).rstrip("/")
    new_urls = []
    for item in new_items:
        if item.get("status") == "deployed":
            slug = item.get("slug") or Path(item["file"]).stem
            new_urls.append({
                "loc": f"{base_url}/knowledge/{slug}",
                "lastmod": datetime.now().strftime("%Y-%m-%d"),
                "changefreq": "weekly",
                "priority": "0.8",
            })
    return new_urls


def submit_to_search_engines(config, new_urls):
    """IndexNow 推送。配置了 key 才发；否则只做记录，不报错。"""
    key = config.get("deployment", {}).get("indexnow_key", "")
    if not key or not new_urls:
        return {"sent": False, "reason": "未配置 indexnow_key 或没有新增 URL"}
    urls = [{"url": u["loc"]} for u in new_urls]
    body = json.dumps({"key": key, "urlList": urls}).encode("utf-8")
    for host in ("api.indexnow.org", "healthlens.cc"):
        try:
            req = urllib.request.Request(
                f"https://{host}/indexnow", data=body,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"sent": True, "host": host, "status": r.status,
                        "count": len(urls)}
        except Exception as e:
            log(f"IndexNow({host}) 失败: {e}", level="WARN")
    return {"sent": False, "reason": "所有 IndexNow 端点失败"}


def generate_seo_summary(deployed_items):
    """生成 SEO 效果预期。"""
    seo_pages = [i for i in deployed_items if i.get("status") == "deployed"]
    return {
        "new_pages": len(seo_pages),
        "expected_impact": "预计 1-2 周内开始获得搜索引擎流量",
        "target_keywords": sum(len(i.get("tags", [])) for i in seo_pages),
        "recommendation": "持续监控 Google Search Console 和百度统计数据",
    }


def run():
    phase = "deploy"
    try:
        start_phase(phase)

        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        state = get_state()
        tasks = [
            t for t in state.get("development_tasks", [])
            if t.get("status") in ("test_passed", "test_warning")
        ]

        if not tasks:
            log("没有可部署的内容，跳过部署阶段")
            complete_phase(phase, output_file=None, items_processed=0)
            return True

        # 1. 真实部署
        deploy_results = deploy_to_server(tasks, config)

        # 2. sitemap
        deployed = [r for r in deploy_results if r["status"] == "deployed"]
        new_sitemap_urls = update_sitemap(deployed, config)

        # 3. 搜索引擎
        seo_summary = generate_seo_summary(deploy_results)
        indexnow = submit_to_search_engines(config, new_sitemap_urls)

        # 4. 更新任务状态
        for result in deploy_results:
            for t in state["development_tasks"]:
                if t["task_id"] == result["task_id"]:
                    t["status"] = (
                        "deployed" if result["status"] == "deployed"
                        else "deploy_failed"
                    )
                    t["deploy_info"] = result
                    break

        deployment_record = {
            "deployment_id": f"deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "items_deployed": len(deployed),
            "items_failed": len(deploy_results) - len(deployed),
            "details": deploy_results,
        }
        state.setdefault("deployment_history", []).append(deployment_record)
        save_state(state)

        # 5. 报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"deploy_{today}",
            "generated_at": datetime.now().isoformat(),
            "channel": "cloudflare_pages",
            "summary": {
                "total_items": len(tasks),
                "deployed": len(deployed),
                "failed": len(deploy_results) - len(deployed),
                "new_urls": new_sitemap_urls,
            },
            "indexnow": indexnow,
            "seo_summary": seo_summary,
            "deployments": deploy_results,
            "next_steps": [
                "监控搜索引擎索引状态",
                "跟踪新页面的流量表现",
                "根据效果优化内容策略",
            ],
        }
        output_file = f"reports/deployed/{today}_deployment_report.json"
        output_path = BASE_DIR / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(deployed),
            deployed_count=len(deployed),
            failed_count=len(deploy_results) - len(deployed),
        )
        log(f"部署完成: {len(deployed)} 项上线")
        return True

    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
