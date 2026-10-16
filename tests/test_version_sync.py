"""tools/sync_version.py 行为契约测试。

动机：agent-card.json 的 version 与 pyproject.toml 漂移已复发两次
（2026-10-15、2026-10-16），此测试锁死工具本身的正确性，防止工具回归。

覆盖：
- --check 一致 → exit 0
- --check 不一致 → exit 1，且不写盘（幂等）
- 写盘模式：不一致 → 修改 version，其他字段保持不变
- 写盘模式：一致 → 不改文件（mtime 不变）
- 输入缺失（pyproject / agent-card）→ exit 1
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "sync_version.py"


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """把 ROOT 的关键文件复制到 tmp_path，改脚本运行目录。

    sync_version.py 用 `Path(__file__).parents[1]` 定位 ROOT，所以只需
    在 tmp_path 里造一个 tools/sync_version.py + 平级的 pyproject.toml
    和 agent-card.json，直接跑那个副本即可，不会影响仓库真文件。
    """
    (tmp_path / "tools").mkdir()
    shutil.copy(TOOL, tmp_path / "tools" / "sync_version.py")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "healthlens"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    (tmp_path / "agent-card.json").write_text(
        json.dumps(
            {"name": "HealthLens", "version": "1.2.3", "extra": {"keep": [1, 2, 3]}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def _run(sandbox: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(sandbox / "tools" / "sync_version.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_check_ok_when_in_sync(sandbox: Path):
    r = _run(sandbox, "--check")
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_check_fails_when_drifted(sandbox: Path):
    card = sandbox / "agent-card.json"
    card.write_text(
        json.dumps(
            {"name": "HealthLens", "version": "9.9.9", "extra": {"keep": [1]}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    before = card.read_text(encoding="utf-8")
    r = _run(sandbox, "--check")
    after = card.read_text(encoding="utf-8")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "ERROR" in r.stderr
    # --check 必须不写盘
    assert before == after, "--check 模式不应修改 agent-card.json"


def test_write_syncs_version_and_preserves_other_fields(sandbox: Path):
    card = sandbox / "agent-card.json"
    original = json.loads(card.read_text(encoding="utf-8"))
    card.write_text(
        json.dumps(
            {"name": "HealthLens", "version": "0.1.0", "extra": {"keep": [1, 2, 3]}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    r = _run(sandbox)  # 默认写盘
    assert r.returncode == 0, r.stderr
    new = json.loads(card.read_text(encoding="utf-8"))
    assert new["version"] == original["version"] == "1.2.3"
    assert new["name"] == original["name"]
    assert new["extra"] == original["extra"]


def test_write_noop_when_in_sync(sandbox: Path):
    card = sandbox / "agent-card.json"
    mtime_before = card.stat().st_mtime
    time.sleep(0.02)  # 确保 mtime 精度区分
    r = _run(sandbox)
    assert r.returncode == 0, r.stderr
    mtime_after = card.stat().st_mtime
    assert mtime_before == mtime_after, "一致时不应触碰文件"


def test_missing_pyproject_errors(sandbox: Path):
    (sandbox / "pyproject.toml").unlink()
    r = _run(sandbox, "--check")
    assert r.returncode == 1
    assert "pyproject.toml" in r.stderr


def test_missing_agent_card_errors(sandbox: Path):
    (sandbox / "agent-card.json").unlink()
    r = _run(sandbox, "--check")
    assert r.returncode == 1
    assert "agent-card.json" in r.stderr


def test_repo_in_sync_currently():
    """回归护栏：仓库当前 agent-card.json 应与 pyproject.toml 一致。

    与 tests/test_agent_card.py::test_version_matches_pyproject_single_source 互补，
    但走的是同一个 sync 工具的路径，避免两处各自漂移。
    """
    r = _run(ROOT, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
