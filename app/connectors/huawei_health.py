"""华为健康数据连接器
Phase 1: OAuth2 授权 + 健康数据拉取骨架
Phase 2: 完整数据同步（步数、心率、睡眠、体重等）

华为健康 API 文档: https://developer.huawei.com/consumer/cn/doc/harmonyos-health-service/
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class HuaweiHealthConnector(BaseConnector):
    """华为健康数据连接器"""

    SOURCE_TYPE = "huawei_health"
    DISPLAY_NAME = "华为健康"
    AUTH_URL = "https://health-health.cloud.huawei.com/hmshealth/auth"
    TOKEN_URL = "https://health-health.cloud.huawei.com/hmshealth/oauth2/v2/token"
    DATA_URL = "https://health-health.cloud.huawei.com/hmshealth/activityservice/v1"

    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None

    def configure(self, client_id: str, client_secret: str, redirect_uri: str):
        """配置华为健康 OAuth2 凭据"""
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        logger.info(f"HuaweiHealth connector configured: client_id={client_id[:8]}...")

    async def get_auth_url(self, state: str) -> str:
        """获取 OAuth2 授权 URL"""
        if not self.client_id:
            raise ValueError("HuaweiHealth connector not configured. Call configure() first.")
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": "openid profile health.activity.read",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query}"

    async def exchange_token(self, code: str) -> dict:
        """用授权码换取 access_token"""
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """刷新 access_token"""
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """拉取健康数据

        Phase 1: 返回模拟数据结构，展示 API 调用方式
        Phase 2: 真实调用华为健康 API
        """
        logger.info(f"Fetching Huawei Health data for last {days} days")

        # Phase 1: 返回模拟数据
        now = datetime.now(timezone.utc)
        items = []
        for i in range(days):
            date = now - timedelta(days=i)
            items.append({
                "date": date.strftime("%Y-%m-%d"),
                "steps": 8500 + (i * 500 % 3000),
                "calories": 1800 + (i * 100 % 600),
                "heart_rate_avg": 72 + (i % 8),
                "heart_rate_max": 120 + (i * 10 % 40),
                "sleep_hours": 7.0 + (i % 3) * 0.5,
                "weight_kg": 70.0 + (i % 5) * 0.2,
                "source": "huawei_health_mock",
            })

        return {
            "items_count": len(items),
            "items": items,
            "message": f"Fetched {days} days of health data (Phase 1 mock)",
        }

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        """同步数据到 HealthLens 格式"""
        days = 7
        if since:
            delta = (datetime.now(timezone.utc) - since).days
            days = min(max(delta, 1), 30)

        data = await self.fetch_health_data(access_token, days)

        # 转换为 HealthObservation 格式
        observations = []
        for item in data["items"]:
            # 步数 → 体力活动指标
            observations.append({
                "loinc_code": "90536-5",
                "loinc_name": "步数(Steps)",
                "value_numeric": item["steps"],
                "value_unit": "步",
                "source": "huawei_health",
                "recorded_at": item["date"],
            })
            # 心率
            observations.append({
                "loinc_code": "8867-4",
                "loinc_name": "心率(Heart Rate)",
                "value_numeric": item["heart_rate_avg"],
                "value_unit": "bpm",
                "source": "huawei_health",
                "recorded_at": item["date"],
            })

        return {
            "items_count": len(observations),
            "observations": observations,
            "message": f"Synced {days} days, extracted {len(observations)} observations",
        }


# 注册连接器
ConnectorRegistry.register("huawei_health", HuaweiHealthConnector)