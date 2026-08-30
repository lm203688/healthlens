"""
数据连接器 API 网关

对接 app/connectors/ 下所有连接器实现，提供：
- GET /api/v1/connectors — 列出所有可用连接器
- GET /api/v1/connectors/{provider} — 获取连接器详情与状态
- POST /api/v1/connectors/{provider}/sync — 触发同步（含脱敏网关）
- POST /api/v1/connectors/{provider}/authenticate — 获取授权 URL

所有同步输出经过脱敏网关，敏感字段默认 mask 级别。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

CONNECTOR_MODULES = [
    ("apple_health", "Apple 健康（XML 导入）"),
    ("huawei_health", "华为健康"),
    ("xiaomi_health", "小米运动健康"),
    ("withings", "Withings"),
    ("hospital_lis", "医院 LIS 系统"),
]


def _load_connector(provider: str):
    """延迟加载连接器模块，返回类。"""
    try:
        mod = importlib.import_module(f"app.connectors.{provider}")
        for name in dir(mod):
            cls = getattr(mod, name)
            if isinstance(cls, type) and name.endswith("Connector"):
                return cls
    except Exception:
        return None
    return None


def list_connectors() -> list[dict]:
    """返回所有可用连接器。"""
    result = []
    for provider, display in CONNECTOR_MODULES:
        connector_cls = _load_connector(provider)
        entry = {
            "provider": provider,
            "display_name": display,
            "available": connector_cls is not None,
            "supports_oauth": False,
            "supports_xml_import": provider == "apple_health",
        }
        if connector_cls:
            entry["supports_oauth"] = hasattr(connector_cls, "get_auth_url")
        result.append(entry)
    return result


def sync_data(provider: str, days: int = 7, desensitize_level: str = "mask") -> dict:
    """
    触发同步。返回同步结果（经过脱敏）。

    当前所有连接器为 mock 实现（返回示例数据），脱敏网关已接入。
    """
    from app.core.desensitize import desensitize_batch, DesensitizeConfig

    connector_cls = _load_connector(provider)
    if connector_cls is None:
        return {"status": "error", "error": f"连接器 '{provider}' 不可用"}

    # 获取示例数据（模拟同步）
    connector = connector_cls()
    if hasattr(connector, "get_sample_data"):
        try:
            raw = connector.get_sample_data()
        except Exception:
            raw = []
    else:
        raw = []

    # 脱敏网关
    config = DesensitizeConfig(level=desensitize_level)
    cleaned = desensitize_batch(raw, config)

    return {
        "status": "ok",
        "provider": provider,
        "display_name": dict(CONNECTOR_MODULES).get(provider, provider),
        "records_raw": len(raw),
        "records_cleaned": len(cleaned),
        "desensitize_level": desensitize_level,
        "sample": cleaned[:3],
    }


def get_auth_url(provider: str, state: str = "random") -> dict | None:
    """获取 OAuth2 授权 URL。"""
    connector_cls = _load_connector(provider)
    if connector_cls is None:
        return None
    connector = connector_cls()
    if not hasattr(connector, "get_auth_url"):
        return {"error": f"{provider} 不支持 OAuth2 授权"}
    try:
        return {"auth_url": connector.get_auth_url(state)}
    except NotImplementedError:
        return {"error": f"{provider} 不支持 OAuth2，请通过其他方式导入"}
    except Exception as exc:
        return {"error": str(exc)}


__all__ = ["list_connectors", "sync_data", "get_auth_url"]