"""通过 GitHub REST API 推送文件（绕开被干扰的 github.com:443）

为什么需要它：
    本机 git push 走 github.com:443，实测 3/3 失败（curl 28 连接重置）；
    但 api.github.com 稳定可达（3/3，0.38s）。
    GitHub 的 Git Data API 允许纯 HTTP 完成 blob→tree→commit→ref 全流程，
    等价于一次 git push，且只依赖 api.github.com。

用法:
    python tools/gh_api_push.py --check                     只验证凭据与仓库
    python tools/gh_api_push.py --files a.yml b.py -m "msg" 推送指定文件
    python tools/gh_api_push.py --dir .github/workflows -m "msg"

Token 来源（按优先级）:
    1. 环境变量 GITHUB_TOKEN
    2. healthlens/.git/config 中 remote.origin.url 内嵌的凭据
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"


def get_token():
    t = os.getenv("GITHUB_TOKEN")
    if t:
        return t, "环境变量 GITHUB_TOKEN"
    cfg = ROOT / "healthlens" / ".git" / "config"
    if cfg.exists():
        m = re.search(r"https://[^:]+:([^@]+)@github\.com", cfg.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1), "healthlens/.git/config（内嵌凭据）"
    return None, None


def get_repo():
    r = os.getenv("GITHUB_REPO")
    if r:
        return r
    cfg = ROOT / "healthlens" / ".git" / "config"
    if cfg.exists():
        m = re.search(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?\s", cfg.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return None


def api(method, path, token, body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "healthlens-deploy")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"message": raw[:300]}


def mask(t):
    return f"{t[:12]}...{t[-4:]}" if t and len(t) > 20 else "***"


def check(token, repo):
    print("=" * 62)
    print("GitHub API 推送通道检查")
    print("=" * 62)
    print(f"\n  仓库   : {repo}")
    print(f"  凭据   : {mask(token)}")

    st, me = api("GET", "/user", token)
    if st != 200:
        print(f"\n  [FAIL] 凭据无效 (HTTP {st}): {me.get('message')}")
        return 1
    print(f"  账号   : {me.get('login')}")

    st, r = api("GET", f"/repos/{repo}", token)
    if st != 200:
        print(f"\n  [FAIL] 无法访问仓库 (HTTP {st}): {r.get('message')}")
        return 1
    perm = r.get("permissions", {})
    print(f"  可见性 : {'public（Actions 免费无限分钟）' if not r.get('private') else 'private（Actions 2000 分钟/月）'}")
    print(f"  默认分支: {r.get('default_branch')}")
    print(f"  权限   : push={perm.get('push')}  admin={perm.get('admin')}")

    if not perm.get("push"):
        print("\n  [FAIL] 凭据没有 push 权限，无法推送")
        return 1

    st, ref = api("GET", f"/repos/{repo}/git/ref/heads/{r.get('default_branch')}", token)
    if st == 200:
        print(f"  远程 HEAD: {ref['object']['sha'][:10]}")

    print("\n  [OK] 推送通道可用 —— 可绕开被干扰的 github.com:443")
    print("=" * 62)
    return 0


def push(token, repo, files, message, branch=None):
    st, r = api("GET", f"/repos/{repo}", token)
    if st != 200:
        print(f"[FAIL] 仓库不可访问: {r.get('message')}")
        return 1
    branch = branch or r.get("default_branch", "main")

    st, ref = api("GET", f"/repos/{repo}/git/ref/heads/{branch}", token)
    if st != 200:
        print(f"[FAIL] 无法读取分支 {branch}: {ref.get('message')}")
        return 1
    base_sha = ref["object"]["sha"]

    st, commit = api("GET", f"/repos/{repo}/git/commits/{base_sha}", token)
    base_tree = commit["tree"]["sha"]

    print(f"仓库 {repo}  分支 {branch}  基点 {base_sha[:10]}")
    print(f"准备推送 {len(files)} 个文件：")

    tree = []
    for f in files:
        p = Path(f)
        if not p.is_file():
            print(f"  [跳过] 不存在: {f}")
            continue
        raw = p.read_bytes()
        st, blob = api("POST", f"/repos/{repo}/git/blobs", token, {
            "content": base64.b64encode(raw).decode(), "encoding": "base64"})
        if st not in (200, 201):
            print(f"  [FAIL] 上传失败 {f}: {blob.get('message')}")
            return 1
        rel = str(p.resolve().relative_to(ROOT)).replace("\\", "/")
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(f"  [OK] {rel}  ({len(raw)} B)")

    if not tree:
        print("没有可推送的文件")
        return 1

    st, newtree = api("POST", f"/repos/{repo}/git/trees", token,
                      {"base_tree": base_tree, "tree": tree})
    if st not in (200, 201):
        print(f"[FAIL] 创建 tree 失败: {newtree.get('message')}")
        return 1

    st, newcommit = api("POST", f"/repos/{repo}/git/commits", token,
                        {"message": message, "tree": newtree["sha"], "parents": [base_sha]})
    if st not in (200, 201):
        print(f"[FAIL] 创建 commit 失败: {newcommit.get('message')}")
        return 1

    st, res = api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", token,
                  {"sha": newcommit["sha"], "force": False})
    if st not in (200, 201):
        print(f"[FAIL] 更新分支失败: {res.get('message')}")
        return 1

    print(f"\n推送成功: {newcommit['sha'][:10]}  {message}")
    print(f"https://github.com/{repo}/commit/{newcommit['sha']}")
    return 0


def _should_skip(path_str, excludes):
    """自动跳过 .git / node_modules / 大体积资产 / 密钥，避免误推"""
    p = Path(path_str)
    parts = p.parts
    if ".git" in parts or "node_modules" in parts or "__pycache__" in parts:
        return True
    if "中医" in parts:                      # 247MB 语料，单独同步
        return True
    low = path_str.lower()
    for ext in (".pdf", ".ttf", ".woff", ".woff2", ".key", ".pem", ".p12", ".pfx"):
        if low.endswith(ext):
            return True
    if parts[-1].lower() in (".env", "secrets.json", "credentials.json"):
        return True
    if excludes:
        for pat in excludes:
            if p.match(pat) or pat in path_str:
                return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--dir")
    ap.add_argument("--manifest")
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("-m", "--message", default="chore: update via API")
    ap.add_argument("--branch")
    a = ap.parse_args()

    token, src = get_token()
    repo = get_repo()
    if not token:
        print("[FAIL] 未找到凭据。请设置环境变量 GITHUB_TOKEN")
        return 1
    if not repo:
        print("[FAIL] 未找到仓库。请设置环境变量 GITHUB_REPO=owner/name")
        return 1

    if a.check:
        print(f"（凭据来源: {src}）")
        return check(token, repo)

    files = list(a.files)
    if a.dir:
        for p in Path(a.dir).rglob("*"):
            if p.is_file() and not _should_skip(str(p), a.exclude):
                files.append(str(p))
    if a.manifest:
        for line in Path(a.manifest).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not _should_skip(line, a.exclude):
                files.append(line)
    if not files:
        print("未指定文件，用 --files / --dir / --manifest")
        return 1
    return push(token, repo, files, a.message, a.branch)


if __name__ == "__main__":
    sys.exit(main())
