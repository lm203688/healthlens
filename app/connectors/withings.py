"""Withings 健康数据连接器
Phase 1: OAuth2 + 数据拉取
Withings API 文档: https://developer.withings.com/api-reference
"""
from datetime import datetime, timezone, timedelta
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class WithingsConnector(BaseConnector):
    """Withings 连接器 - 体重秤/血压计/睡眠监测"""

    SOURCE_TYPE = "withings"
    DISPLAY_NAME = "Withings"
    AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
    TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
    DATA_URL = "https://wbsapi.withings.net/measure"

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
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user.info,user.metrics,user.activity",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query}"

    async def exchange_token(self, code: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "action": "requesttoken",
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("body", {})

    async def refresh_access_token(self, refresh_token: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "action": "requesttoken",
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            return resp.json().get("body", {})

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """拉取 Withings 测量数据"""
        import httpx

        now = datetime.now(timezone.utc)
        start = int((now - timedelta(days=days)).timestamp())
        end = int(now.timestamp())

        # Phase 1: 返回模拟数据结构
        # Phase 2: 真实调用 withings API
        logger.info(f"Fetching Withings data for {days} days (mock)")

        items = []
        for i in range(days):
            date = now - timedelta(days=i)
            items.append({
                "date": date.strftime("%Y-%m-%d"),
                "weight_kg": 70.0 + (i % 5) * 0.3,
                "body_fat_pct": 22.0 + (i % 3) * 0.5,
                "systolic": 118 + (i % 10),
                "diastolic": 78 + (i % 8),
                "heart_rate": 68 + (i % 6),
                "source": "withings_mock",
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
                "loinc_code": "29463-7", "loinc_name": "体重(Body Mass)",
                "value_numeric": item["weight_kg"], "value_unit": "kg",
                "source": "withings", "recorded_at": item["date"],
            })
            observations.append({
                "loinc_code": "8480-6", "loinc_name": "收缩压(Systolic)",
                "value_numeric": item["systolic"], "value_unit": "mmHg",
                "source": "withings", "recorded_at": item["date"],
            })
            observations.append({
                "loinc_code": "8462-4", "loinc_name": "舒张压(Diastolic)",
                "value_numeric": item["diastolic"], "value_unit": "mmHg",
                "source": "withings", "recorded_at": item["date"],
            })

        return {
            "items_count": len(observations),
            "observations": observations,
            "message": f"Synced {days} days, {len(observations)} observations",
        }


ConnectorRegistry.register("withings", WithingsConnector)
