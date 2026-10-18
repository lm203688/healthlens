"""单一版本真源（S3-5 工程债，2026-10-13）。

背景：版本号此前同时硬编码在 `pyproject.toml`（0.25.0）与
`app/config.py`（APP_VERSION=0.25.0），而 CHANGELOG 已推进到 0.26.1——
三处漂移，发布时无法判断真实版本。

本模块把版本收敛为**唯一真源**：`pyproject.toml` 的 `[project].version`。
`app.config.Settings.APP_VERSION` 改为引用本模块，从此不可能再漂移。
`tests/core/test_version.py` 额外断言 CHANGELOG 顶部版本与之一致，
作为 CI 门禁防止回归。

设计约束：
- 只读标准库（tomllib / pathlib），无第三方依赖，可在导入期安全执行。
- 读不到时**不静默伪造**版本号：返回显式标记的回退值 `_FALLBACK`，
  调用方可据此发现「版本源不可解析」这一故障，而非拿到一个看似正常的假版本。
"""
from __future__ import annotations

import tomllib
from pathlib import Path

# app/core/version.py -> parents[0]=core, parents[1]=app, parents[2]=仓库根
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# 显式标记的回退值：任何正常部署都不应出现它，出现即代表版本源解析失败。
_FALLBACK = "0.0.0+unresolved"

_APP_NAME = "HealthLens"


def read_pyproject_version() -> str:
    """读取 `pyproject.toml` 的 `[project].version`。

    失败时返回 `_FALLBACK`（不抛异常、不编造版本号），
    以便在测试环境或缺文件场景下仍可导入，同时故障可被观测。
    """
    try:
        data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        raw = data["project"]["version"]
        if not isinstance(raw, str) or not raw.strip():
            return _FALLBACK
        return raw.strip()
    except Exception:
        return _FALLBACK


#: 应用版本号（模块导入时求值一次）。
__version__ = read_pyproject_version()

#: 版本是否成功解析自 pyproject.toml（用于自检与审计）。
version_resolved: bool = __version__ != _FALLBACK


def version_info() -> dict:
    """运行时版本信息（供 `/api/v1/version` 与 A2A agent-card 引用）。"""
    info = {
        "app": _APP_NAME,
        "version": __version__,
        "version_source": "pyproject.toml [project].version",
        "version_resolved": version_resolved,
    }
    # 仅在实际有值时附带仓库根，避免在打包产物中泄露构建路径。
    if version_resolved:
        info["version_file"] = str(_PYPROJECT)
    return info


if __name__ == "__main__":  # 便于人工核对：python -m app.core.version
    for k, v in version_info().items():
        print(f"{k}: {v}")
