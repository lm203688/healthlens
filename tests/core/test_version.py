"""版本单一真源门禁（S3-5，2026-10-13）。

阻断版本漂移回归：版本号只能定义一次（`pyproject.toml` 的
`[project].version`），`Settings.APP_VERSION`、`app.core.version.__version__`、
CHANGELOG 顶部条目必须与它一致。历史上三者曾同时存在且漂移
（pyproject/config=0.25.0 而 CHANGELOG 已 0.26.1），导致无法判断真实版本。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_CHANGELOG_HEADER = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def _pyproject_version() -> str:
    import tomllib

    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _changelog_top_version() -> str:
    text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = _CHANGELOG_HEADER.search(text)
    assert m, "CHANGELOG.md 缺少 '## [x.y.z]' 顶部版本条目"
    return m.group(1)


class TestSingleVersionSource:
    """版本号单一真源：pyproject.toml。"""

    def test_pyproject_is_the_source_of_truth(self):
        import app.core.version as v

        assert v.__version__ == _pyproject_version()

    def test_version_resolved_not_fallback(self):
        """版本必须成功解析，不允许出现未解析回退值（静默伪造版本）。"""
        import app.core.version as v

        assert v.version_resolved is True
        assert v.__version__ != v._FALLBACK

    def test_settings_app_version_matches_pyproject(self):
        from app.config import settings

        assert settings.APP_VERSION == _pyproject_version()

    def test_changelog_top_matches_pyproject(self):
        """CHANGELOG 顶部版本必须与 pyproject 一致（发布门禁）。"""
        assert _changelog_top_version() == _pyproject_version()

    def test_version_info_shape(self):
        from app.core.version import version_info

        info = version_info()
        assert info["app"] == "HealthLens"
        assert info["version"] == _pyproject_version()
        assert info["version_resolved"] is True
        assert info["version_source"] == "pyproject.toml [project].version"


class TestVersionEndPoints:
    """运行时版本端点暴露同一个真源。"""

    @pytest.mark.asyncio
    async def test_version_endpoint_matches_source(self, client):
        resp = await client.get("/api/v1/version")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == _pyproject_version()
        assert body["version_resolved"] is True

    @pytest.mark.asyncio
    async def test_health_endpoint_shares_same_version(self, client):
        """`/health` 与新 `/api/v1/version` 必须返回同一版本值（无第二真源）。"""
        health = (await client.get("/health")).json()
        version = (await client.get("/api/v1/version")).json()
        assert health["version"] == version["version"] == _pyproject_version()
