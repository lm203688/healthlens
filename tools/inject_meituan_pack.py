#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把"修复食材包"组件注入 3 篇 GEO 长文，并触发 CF Pages 部署。
前置：用户在美团联盟(union.meituan.com)注册并拿到推广位 PID。
用法：
  set MEITUAN_PID=你的PID
  python tools/inject_meituan_pack.py
依赖：tools/cf_pages_deploy.py（需 CLOUDFLARE token，见 .workbuddy/cache/cf_tokens.json）
"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "auto-pipeline", "content", "generated")
COMP = os.path.join(ROOT, "HealthLens_美团修复食材包_组件.html")
PAGES = ["cell-repair-non-drug", "autophagy-activation", "mitochondrial-health"]

CF_TOKEN = os.environ.get("CF_PAGES_TOKEN", "")
if not CF_TOKEN:
    # 不在源码里硬编码令牌；从 gitignored 本地缓存读取（.workbuddy/cache/cf_tokens.json）
    _cache = os.path.join(ROOT, ".workbuddy", "cache", "cf_tokens.json")
    try:
        import json
        _toks = json.load(open(_cache, encoding="utf-8")).get("tokens", [])
        # 优先取第二个令牌（对该项目有 Pages 部署权限）
        CF_TOKEN = _toks[1] if len(_toks) > 1 else (_toks[0] if _toks else "")
    except Exception:
        CF_TOKEN = ""
CF_ACC = os.environ.get("CF_ACCOUNT_ID", "8162aa3b2241c132e43a81f526d7f758")


def main():
    pid = os.environ.get("MEITUAN_PID", "").strip()
    if not pid:
        print("❌ 缺少 MEITUAN_PID 环境变量（美团联盟推广位 PID）")
        sys.exit(2)
    tpl = open(COMP, encoding="utf-8").read()
    # 去掉 HTML 注释里的占位说明，保留 <section> + <style>
    block = tpl.split("-->", 1)[1].strip() if "-->" in tpl else tpl
    block = block.replace("{{MEITUAN_PID}}", pid)

    for name in PAGES:
        html = os.path.join(GEN, name + ".html")
        txt = open(html, encoding="utf-8").read()
        if "recovery-pack" in txt:
            print(f"  [skip] {name} 已注入")
            continue
        marker = '  <div class="disclaimer">'
        if marker not in txt:
            print(f"  [WARN] {name} 未找到注入锚点，跳过")
            continue
        txt = txt.replace(marker, block + "\n\n" + marker, 1)
        open(html, "w", encoding="utf-8").write(txt)
        print(f"  [ok] {name} 注入修复食材包 (PID={pid})")

    print("[deploy] 重新部署到 CF Pages ...")
    env = os.environ.copy()
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "cf_pages_deploy.py"),
         "--token", CF_TOKEN, "--account-id", CF_ACC, "--project", "healthlens"],
        cwd=ROOT, env=env)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
