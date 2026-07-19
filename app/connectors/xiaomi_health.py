"""小米运动健康数据连接器
Phase 1: OAuth2 + 数据拉取骨架
小米运动健康 API 文档: https://dev.mi.com/console/doc/detail?pId=2309
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class XiaomiHealthConnector(BaseConnector):
    """小米运动健康连接器 - 手环/体重秤"""

    SOURCE_TYPE = "xiaomi_health"
    DISPLAY_NAME = "小米运动健康"
    AUTH_URL = "https://account.xiaomi.com/oauth2/authorize"
    TOKEN_URL = "https://account.xiaomi.com/oauth2/token"
    DATA_URL = "https://api.mi.com/v1"

    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None

    def configure(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    async def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "1 6000",  # 小米运动健康 scope
            "state": state,
            "skip_confirm": "true",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query}"

    async def exchange_token(self, code: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """拉取小米运动健康数据"""
        logger.info(f"Fetching Xiaomi Health data for {days} days (mock)")

        now = datetime.now(timezone.utc)
        items = []
        for i in range(days):
            date = now - timedelta(days=i)
            items.append({
                "date": date.strftime("%Y-%m-%d"),
                "steps": 7000 + (i * 800 % 4000),
                "heart_rate_avg": 70 + (i % 10),
                "sleep_hours": 6.5 + (i % 3) * 0.5,
                "source": "xiaomi_health_mock",
            })

        return {
            "items_count": len(items),
            "items": items,
            "message": f"Fetched {days} days (Phase 1 mock)",
        }

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        days = 7
        if since:
            delta = (datetime.now(timezone.utc) - since).days
            days = min(max(delta, 1), 30)

        data = await self.fetch_health_data(access_token, days)

        observations = []
        for item in data["items"]:
            observations.append({
                "loinc_code": "90536-5", "loinc_name": "步数(Steps)",
                "value_numeric": item["steps"], "value_unit": "步",
                "source": "xiaomi_health", "recorded_at": item["date"],
            })
            observations.append({
                "loinc_code": "8867-4", "loinc_name": "心率(Heart Rate)",
                "value_numeric": item["heart_rate_avg"], "value_unit": "bpm",
                "source": "xiaomi_health", "recorded_at": item["date"],
            })

        return {
            "items_count": len(observations),
            "observations": observations,
            "message": f"Synced {days} days, {len(observations)} observations",
        }


ConnectorRegistry.register("xiaomi_health", XiaomiHealthConnector)
