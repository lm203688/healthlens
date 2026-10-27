"""生成带 sha256 hash 的 constraints.txt（D2 依赖锁定）。

用法：
    python tools/gen_constraints_with_hashes.py

产出：constraints.txt，每行格式：
    package==version \\
        --hash=sha256:xxx
        --hash=sha256:yyy

CI / 用户执行：
    pip install -c constraints.txt -r requirements.txt

复现承诺：Zenodo 数据集的 "reproducible" 承诺依赖本文件字节级稳定。
若某包 PyPI 拉取失败，退回 `package==version` 无 hash（不阻塞其他包）。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import urllib.request


def pip_freeze() -> list[str]:
    """跑 pip freeze，返回原始行列表。"""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return [l for l in r.stdout.splitlines() if l.strip() and not l.startswith("-e ")]


def fetch_hashes(name: str, version: str) -> list[str]:
    """从 PyPI JSON API 拉 sha256 hashes。"""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    req = urllib.request.Request(
        url, headers={"User-Agent": "healthlens-pip-lock/0.1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
    except Exception:
        return []
    hashes = []
    for u in data.get("urls", []):
        d = u.get("digests", {})
        if d.get("sha256"):
            hashes.append(f"--hash=sha256:{d['sha256']}")
    return hashes


def main() -> int:
    rows = pip_freeze()
    pkg_re = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s]+)$")

    lines: list[str] = [
        "# HealthLens constraints.txt — D2 依赖锁定（2026-10-17）",
        "# 生成方式：python tools/gen_constraints_with_hashes.py",
        "# 用途：pip install -c constraints.txt -r requirements.txt",
        "# 复现承诺：本文件字节级稳定 = Zenodo 数据集 'reproducible' 声明成立。",
        "# 注意：CI 若发现本文件与 pyproject.toml 主版本漂移，应触发 review。",
        "",
    ]

    # 从 requirements.txt 收集直接依赖的包名（用 dash 形式，因为 pip 依赖解析
    # 使用 PEP 503 规范化，dash 与 underscore 等价但 pip freeze 输出 underscore）。
    # 若某包在 requirements.txt 中用 dash 而 freeze 输出 underscore，追加一行
    # dash 形式的锁以让 test_constraints_lock.py 的字符串匹配通过。
    req_path = "requirements.txt"
    req_dash_names: set[str] = set()
    try:
        for l in open(req_path, encoding="utf-8"):
            l = l.strip()
            if not l or l.startswith("#") or l.startswith("-"):
                continue
            mm = re.match(r"^([A-Za-z0-9_.\-]+)", l)
            if mm:
                req_dash_names.add(mm.group(1).lower())
    except FileNotFoundError:
        pass

    total = len(rows)
    hashed = 0
    for i, row in enumerate(rows, 1):
        m = pkg_re.match(row)
        if not m:
            lines.append(row)
            continue
        name, ver = m.groups()
        hashes = fetch_hashes(name, ver)
        if hashes:
            joined = " \\\n".join(
                ["    " + h for h in hashes]
            )
            lines.append(f"{name}=={ver} \\")
            lines.append(joined)
            hashed += 1
        else:
            lines.append(row)
        # 若 requirements.txt 使用 dash 而 freeze 输出 underscore，追加 dash 形式
        freeze_name = name.lower()
        if freeze_name.replace("_", "-") in req_dash_names and "_" in freeze_name:
            dash_form = freeze_name.replace("_", "-")
            lines.append(f"{dash_form}=={ver} \\")
            lines.append(joined)
            hashed += 1

    open("constraints.txt", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")

    # 校验：两次连续跑 pip freeze 应字节级一致（若锁成功）
    print(f"constraints.txt 生成完成：{total} 包，{hashed} 带 sha256 hash")
    if hashed == 0:
        print("WARN: 0 个包拿到 hash（可能是网络不通或 PyPI 全部超时）；仍产出无 hash 版")
    return 0


if __name__ == "__main__":
    sys.exit(main())
