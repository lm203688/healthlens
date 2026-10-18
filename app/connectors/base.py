"""数据源连接器基类
所有外部数据源（Apple Health, Withings, 华为健康, 小米运动健康, 医院LIS 等）的统一抽象。
"""
from dataclasses import dataclass
from datetime import datetime
from loguru import logger
from typing import Any


@dataclass
class SyncResult:
    success: bool
    records_count: int
    errors: list[str]
    synced_at: datetime
    raw_data: list[dict[str, Any]] | None = None


class BaseConnector:
    """数据源连接器基类

    子类应实现以下方法（按需）：
    - configure(client_id, client_secret, redirect_uri) — OAuth2 配置
    - get_auth_url(state) — 获取授权 URL
    - exchange_token(code) — 授权码换 token
    - refresh_access_token(refresh_token) — 刷新 token
    - fetch_health_data(access_token, days) — 拉取数据
    - sync_data(access_token, user_id, since) — 同步数据到 HealthObservation 格式
    """

    SOURCE_TYPE: str = "base"
    DISPLAY_NAME: str = "Base Connector"

    def configure(self, *args, **kwargs):
        """配置连接器凭据"""
        raise NotImplementedError(f"{self.SOURCE_TYPE} connector does not support configure()")

    async def get_auth_url(self, state: str) -> str:
        raise NotImplementedError(f"{self.SOURCE_TYPE} connector does not support OAuth2")

    async def exchange_token(self, code: str) -> dict:
        raise NotImplementedError(f"{self.SOURCE_TYPE} connector does not support OAuth2")

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        raise NotImplementedError(f"{self.SOURCE_TYPE} connector does not support fetch_health_data()")

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        """同步数据 - 子类应实现"""
        raise NotImplementedError(f"{self.SOURCE_TYPE} connector does not support sync_data()")


class ConnectorRegistry:
    """连接器注册表 - 管理所有可用数据源连接器"""

    _connectors: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, source_type_or_cls: str | type[BaseConnector], connector_cls: type[BaseConnector] | None = None):
        """注册连接器
        用法1: @ConnectorRegistry.register("name") 装饰器形式
        用法2: ConnectorRegistry.register("name", MyClass) 直接调用
        """
        if connector_cls is not None:
            cls._connectors[source_type_or_cls] = connector_cls
            return connector_cls
        else:
            def decorator(connector_cls: type[BaseConnector]):
                cls._connectors[source_type_or_cls] = connector_cls
                return connector_cls
            return decorator

    @classmethod
    def get(cls, source_type: str) -> BaseConnector | None:
        connector_cls = cls._connectors.get(source_type)
        if connector_cls:
            return connector_cls()
        return None

    @classmethod
    def available_sources(cls) -> list[str]:
        return list(cls._connectors.keys())
