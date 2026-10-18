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
        """拉取小米运动健康数据（真实 API）。

        S1-5 反骨架化：缺凭据时诚实报错，绝不返回 mock。
        上一版 Phase 1 以 `xiaomi_health_mock` 生成数据，违反项目
        「骨架未接线时必须 fail-loud」原则——已移除。
        """
        import httpx

        if not self.client_id or not self.client_secret:
            return {
                "items_count": 0,
                "items": [],
                "error": "小米运动健康未配置：请在环境变量设置 XIAOMI_HEALTH_CLIENT_ID 和 XIAOMI_HEALTH_CLIENT_SECRET",
                "message": "连接器不可用——需先配置 OAuth2 凭据",
            }
        if not access_token:
            return {
                "items_count": 0,
                "items": [],
                "error": "缺少 access_token",
                "message": "请引导用户完成 OAuth2 授权后重试",
            }

        logger.info(f"Fetching Xiaomi Health data for {days} days (real API)")

        now = datetime.now(timezone.utc)
        start = int((now - timedelta(days=days)).timestamp())
        end = int(now.timestamp())

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.DATA_URL}/stats/query",
                    params={
                        "access_token": access_token,
                        "start_time": start,
                        "end_time": end,
                        "types": "steps,heart_rate,sleep",
                        "aggregate": "daily",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            records = data.get("data") or data.get("stats") or []
            items = []
            for rec in records:
                items.append({
                    "date": rec.get("date", "")[:10],
                    "steps": rec.get("steps", 0),
                    "heart_rate_avg": rec.get("heart_rate_avg", 0),
                    "sleep_hours": rec.get("sleep_hours", 0),
                    "source": "xiaomi_health",
                })

            return {
                "items_count": len(items),
                "items": items,
                "message": f"Fetched {len(items)} records from Xiaomi Health ({days} days)",
            }
        except httpx.HTTPStatusError as exc:
            logger.error(f"Xiaomi Health API HTTP error: {exc.response.status_code}")
            return {
                "items_count": 0,
                "items": [],
                "error": f"Xiaomi Health API HTTP {exc.response.status_code}",
                "message": "小米健康 API 请求失败",
            }
        except Exception as exc:
            logger.error(f"Xiaomi Health API error: {exc}")
            return {
                "items_count": 0,
                "items": [],
                "error": str(exc),
                "message": "小米健康 API 异常",
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
