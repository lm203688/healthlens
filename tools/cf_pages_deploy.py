#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HealthLens -> Cloudflare Pages 部署脚本（封装官方 wrangler，最可靠）。

为什么用 wrangler 而非手写 API 直传：
  手写 multipart 直传（POST .../deployments）在本环境实测会被 Cloudflare
  接受返回 success，但文件实际未落盘、线上全 404（坑）。wrangler 是它的
  官方封装，multipart 格式正确，47 个文件全部正常服务。

用法:
  python tools/cf_pages_deploy.py
    [--no-build]                       # 跳过构建（默认会先构建）
    [--account-id ID]                  # 默认 CLOUDFLARE_ACCOUNT_ID
    [--token TOKEN]                    # 默认 CLOUDFLARE_API_TOKEN
    [--project healthlens]
    [--dist auto-pipeline/dist]

依赖（隔离环境，已预装）:
  C:/Users/xing/.workbuddy/binaries/node/workspace/node_modules/wrangler
  + managed node 22.22.2
凭据（Cloudflare API Token，需 Account - Cloudflare Pages - Edit，绑定账号 8162aa3b）:
  见环境变量 CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID
"""
import os
import sys
import shutil
import subprocess
import argparse
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = "C:/Users/xing/.workbuddy/binaries/node/versions/22.22.2/node.exe"
WRANGLER_JS = (
    os.environ.get("WRANGLER_JS")
    or "C:/Users/xing/.workbuddy/binaries/node/workspace/node_modules/wrangler/bin/wrangler.js"
)
BUILD_SCRIPT = os.path.join(
    ROOT, "auto-pipeline", "scripts", "phase_6_deploy", "build_site.py"
)
PY = sys.executable


def build() -> str:
    """构建到全新的一次性目录，并返回该目录的真实路径。

    为什么必须显式指定 --out：build_site.py 在 auto-pipeline/dist 非空时会
    自动改用一次性输出目录；若调用方仍按硬编码的 dist 去部署，就会把上一版
    陈旧产物再上传一遍 —— 新产物永远无法上线（此前长期如此）。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(ROOT, "auto-pipeline", f"dist_build_{ts}")
    print(f"[build] 构建静态产物 -> {out}")
    r = subprocess.run([PY, BUILD_SCRIPT, "--out", out], cwd=ROOT)
    if r.returncode != 0:
        print("❌ 构建失败，中止部署")
        sys.exit(r.returncode)
    if not os.path.isdir(out):
        print(f"❌ 构建产物目录不存在: {out}")
        sys.exit(2)
    n = sum(len(files) for _, _, files in os.walk(out))
    print(f"[build] OK -> {out}（{n} 个文件）")
    return out


def promote(out: str):
    """部署成功后把新产物转正为 auto-pipeline/dist，并清理历史目录。

    用 rename 而非删除：既避免误删已上线产物的风险，也让回滚随时可行。
    """
    ap = os.path.join(ROOT, "auto-pipeline")
    final = os.path.join(ap, "dist")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        if os.path.isdir(final):
            os.rename(final, os.path.join(ap, f"dist_prev_{ts}"))
        os.rename(out, final)
        print(f"[promote] 新产物已转正 -> {final}")
    except OSError as e:
        print(f"[promote][WARN] 转正失败（部署已成功，可手动处理）: {e}")
        return
    for prefix in ("dist_build_", "dist_prev_"):
        olds = sorted(
            [d for d in os.listdir(ap) if d.startswith(prefix)], reverse=True
        )
        for d in olds[3:]:
            shutil.rmtree(os.path.join(ap, d), ignore_errors=True)


def deploy(account_id: str, token: str, project: str, dist: str):
    if not os.path.isfile(WRANGLER_JS):
        print(f"❌ 找不到 wrangler: {WRANGLER_JS}\n   请先在隔离工作区安装: "
              f"cd C:/Users/xing/.workbuddy/binaries/node/workspace && "
              f"npm install wrangler@3")
        sys.exit(2)
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = token
    env["CLOUDFLARE_ACCOUNT_ID"] = account_id
    cmd = [
        NODE, WRANGLER_JS, "pages", "deploy", dist,
        "--project-name", project,
        "--branch", "main",
        "--commit-dirty=true",
    ]
    print("[deploy] wrangler pages deploy ...")
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        print("❌ 部署失败 (wrangler exit %d)" % r.returncode)
        sys.exit(r.returncode)
    print("✅ 部署完成")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-id", default=os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))
    ap.add_argument("--token", default=os.environ.get("CLOUDFLARE_API_TOKEN", ""))
    ap.add_argument("--project", default="healthlens")
    ap.add_argument("--dist", default=os.path.join(ROOT, "auto-pipeline", "dist"))
    ap.add_argument("--no-build", action="store_true", help="跳过构建步骤")
    args = ap.parse_args()

    if not args.account_id:
        print("❌ 缺少 --account-id（Cloudflare 32位账户ID，8162aa3b...）")
        sys.exit(2)
    if not args.token:
        print("❌ 缺少 --token（Cloudflare API Token，cfut_ 开头，需绑定 8162aa3b）")
        sys.exit(2)

    if not args.no_build:
        dist = build()
    else:
        dist = args.dist
    deploy(args.account_id, args.token, args.project, dist)
    if not args.no_build:
        promote(dist)


if __name__ == "__main__":
    main()
