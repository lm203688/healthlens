"""Biomni 生物医学证据 Adapter —— L4 评估层

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「外部证据工具：Biomni（Apache-2.0，Science 2026-07，★3.9k，极活跃）」。

定位：
- **薄 Adapter**：只暴露 `query_biomedical_claim(claim)`，屏蔽 Biomni 内部结构。
- **未装即 fail-loud**：无 Biomni 时抛 `HealthLensUnavailableEngine`，
  让上层明确告知用户安装方式。
- **不承诺 biomni 已公开发布**：pyproject.toml 的 `[project.optional-dependencies]`
  中**未**加 biomni（报告指出「可能未公开发布」），本 adapter 通过探测 +
  明确异常暴露当前不可用状态。

Wellness 平台术语纪律：本模块只做外部证据检索，不做诊断/治疗判断。

作者：HealthLens L4 评估团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import importlib.util
from typing import Any

from app.lib.engine_exceptions import HealthLensUnavailableEngine


_ENGINE_NAME = "biomni"
_REQUIRED_PACKAGE = "biomni"
# 报告明确：biomni 可能未公开发布，故 extra_hint=None（无 [project.optional-dependencies] 里对应 extra）
_EXTRA_HINT: str | None = None


def _biomni_available() -> bool:
    return importlib.util.find_spec("biomni") is not None


def _require_biomni():
    if not _biomni_available():
        raise HealthLensUnavailableEngine(
            engine_name=_ENGINE_NAME,
            required_package=_REQUIRED_PACKAGE,
            extra_hint=_EXTRA_HINT,
            detail=(
                "Biomni 未在 pyproject.toml 的 [project.optional-dependencies] 中声明"
                "（报告 §5 L4 指出其可能未公开发布）。"
                "若已获取本地 biomni 包，请 `pip install biomni`。"
            ),
        )
    import biomni  # type: ignore[import-not-found]

    return biomni


def probe() -> dict[str, Any]:
    """探测 Biomni 是否可用（供 API /probe 端点使用）。"""
    avail = _biomni_available()
    version = None
    if avail:
        try:
            import biomni  # type: ignore[import-not-found]

            version = getattr(biomni, "__version__", None)
        except Exception:  # noqa: BLE001
            version = None
    return {
        "engine": _ENGINE_NAME,
        "available": avail,
        "version": version,
        "install_hint": "pip install biomni（可能未公开发布，参见报告 §5 L4）",
        "note": (
            "Biomni 已装"
            if avail
            else "Biomni 未装；query_biomedical_claim 将抛 HealthLensUnavailableEngine"
        ),
    }


def query_biomedical_claim(claim: str, **kwargs: Any) -> dict[str, Any]:
    """查询外部生物医学证据（Biomni）。

    报告定位（§5 L4）：Biomni 是外部证据工具层，用于给 rubric 判断提供
    独立证据来源，验证答案是否引用了权威文献。

    Args:
        claim: 待查询的生物医学 claim（英文/中文均可）
        **kwargs: 透传给 Biomni 的额外参数

    Returns:
        结构化证据 dict：
        {
            "claim": 原始 claim,
            "found": bool,
            "score": float,          # 相关性分数（0-1）
            "sources": [             # 命中的文献/条目
                {"id": str, "title": str, "snippet": str, "score": float}
            ],
            "engine": "biomni",
            "note": str,             # 简短说明
        }

    Raises:
        HealthLensUnavailableEngine: biomni 未安装或调用失败
        ValueError: claim 为空或类型错误
    """
    _require_biomni()
    if not isinstance(claim, str):
        raise ValueError(f"claim must be str, got {type(claim).__name__}")
    if not claim.strip():
        raise ValueError("claim must be non-empty")

    try:
        import biomni  # type: ignore[import-not-found]

        # Biomni 公开 API 不稳定；此处按常见形态尝试 3 种入口，任一成功即返回。
        result_obj = None
        if hasattr(biomni, "query"):
            result_obj = biomni.query(claim, **kwargs)
        elif hasattr(biomni, "search"):
            result_obj = biomni.search(claim, **kwargs)
        elif hasattr(biomni, "Client"):
            client = biomni.Client()
            result_obj = client.query(claim, **kwargs)
        else:
            # 未知 API 形态
            return {
                "claim": claim,
                "found": False,
                "score": 0.0,
                "sources": [],
                "engine": _ENGINE_NAME,
                "note": f"biomni module has no known API (query/search/Client); version={getattr(biomni, '__version__', 'unknown')}",
            }

        # 归一化返回结构
        sources: list[dict[str, Any]] = []
        if isinstance(result_obj, dict):
            for item in result_obj.get("results", result_obj.get("sources", [])) or []:
                if isinstance(item, dict):
                    sources.append({
                        "id": str(item.get("id", "")),
                        "title": str(item.get("title", "")),
                        "snippet": str(item.get("snippet", item.get("text", ""))),
                        "score": float(item.get("score", 0.0) or 0.0),
                    })
        elif isinstance(result_obj, list):
            for item in result_obj:
                if isinstance(item, dict):
                    sources.append({
                        "id": str(item.get("id", "")),
                        "title": str(item.get("title", "")),
                        "snippet": str(item.get("snippet", item.get("text", ""))),
                        "score": float(item.get("score", 0.0) or 0.0),
                    })
        top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
        return {
            "claim": claim,
            "found": bool(sources),
            "score": top_score,
            "sources": sources,
            "engine": _ENGINE_NAME,
            "note": f"queried via biomni v{getattr(biomni, '__version__', 'unknown')}",
        }
    except HealthLensUnavailableEngine:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HealthLensUnavailableEngine(
            engine_name=_ENGINE_NAME,
            required_package=_REQUIRED_PACKAGE,
            detail=f"query_biomedical_claim failed: {type(exc).__name__}: {exc}",
        ) from exc


__all__ = [
    "query_biomedical_claim",
    "probe",
    "HealthLensUnavailableEngine",
]
