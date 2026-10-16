"""以 pyproject.toml 为单一真源同步 agent-card.json 的版本号。

背景：agent-card.json 的 version 曾多次与 pyproject.toml 漂移（2026-10-15、
2026-10-16 各手工修一次），虽然 `tests/test_agent_card.py::
test_version_matches_pyproject_single_source` 能抓到，但只在 pytest 阶段暴露，
且不会自动修复。此工具把版本 bump 变成一次调用：

    # 交互/本地：直接写回 agent-card.json
    python tools/sync_version.py

    # CI 门禁：只检查，不一致就 exit 1，不修改任何文件
    python tools/sync_version.py --check

行为细节：
- 只改 agent-card.json 顶层的 `version` 字段，其他键一字不改。
- 保留原文件的缩进风格（当前是 2 空格）与末尾换行。
- 若 pyproject.toml 里没有 `project.version` 或缺失 agent-card.json，
  直接 exit 1（不该静默成功）。
- `--check` 模式永远不写盘，方便 CI 用；`--write` 是默认行为。
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CARD = ROOT / "agent-card.json"


def read_pyproject_version() -> str:
    with open(PYPROJECT, "rb") as f:
        data = tomllib.load(f)
    v = data.get("project", {}).get("version")
    if not v:
        raise SystemExit("pyproject.toml 缺少 [project].version")
    return v


def sync(check: bool) -> int:
    if not PYPROJECT.is_file():
        print(f"错误：找不到 {PYPROJECT}", file=sys.stderr)
        return 1
    if not CARD.is_file():
        print(f"错误：找不到 {CARD}", file=sys.stderr)
        return 1

    want = read_pyproject_version()
    text = CARD.read_text(encoding="utf-8")
    card = json.loads(text)
    cur = card.get("version")

    if cur == want:
        print(f"OK: agent-card.json version == pyproject.version == {want}")
        return 0

    if check:
        print(
            f"ERROR: agent-card.json version={cur!r} 与 pyproject "
            f"version={want!r} 不一致。运行 `python tools/sync_version.py` 修复。",
            file=sys.stderr,
        )
        return 1

    card["version"] = want
    # 保留原缩进风格：探测原文件首行的分隔符。
    indent = "  "
    for line in text.splitlines():
        if ":" in line and line.strip().startswith('"'):
            # 找到第一个包含引号 key 的缩进行
            stripped = line.lstrip()
            if stripped != line:
                indent = line[: len(line) - len(stripped)]
                break
    new_text = json.dumps(card, ensure_ascii=False, indent=len(indent)) + "\n"
    CARD.write_text(new_text, encoding="utf-8")
    print(f"OK: agent-card.json version {cur!r} -> {want!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="同步 agent-card.json version 到 pyproject")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只检查，不写盘；不一致 exit 1")
    g.add_argument("--write", action="store_true", help="写盘（默认行为，此 flag 仅用于显式表达）")
    args = p.parse_args(argv)
    return sync(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
