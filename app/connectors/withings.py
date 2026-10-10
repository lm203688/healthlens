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
        """拉取 Withings 测量数据（真实 API）

        P0-7：配置凭据后调用 Withings 真实 API 拉取数据。
        缺凭据时诚实报错，绝不返回 mock。
        """
        import httpx

        now = datetime.now(timezone.utc)
        start = int((now - timedelta(days=days)).timestamp())
        end = int(now.timestamp())

        if not self.client_id or not self.client_secret:
            return {
                "items_count": 0,
                "items": [],
                "error": "Withings 未配置：请在环境变量设置 WITHINGS_CLIENT_ID 和 WITHINGS_CLIENT_SECRET",
                "message": "连接器不可用——需先配置 OAuth2 凭据",
            }

        logger.info(f"Fetching Withings data for {days} days (real API)")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self.DATA_URL,
                    data={
                        "access_token": access_token,
                        "measured_kind": "250,524,3025,3026",  # weight(250), systolic(524), heart_rate(3025), diastolic(3026)
                        "date": start,
                        "enddate": end,
                        "category": "all",
                        "details": "false",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") != 0:
                    return {
                        "items_count": 0,
                        "items": [],
                        "error": f"Withings API error: status={data.get('status')}",
                        "message": "Withings API 返回错误",
                    }

                items = []
                for series in data.get("body", {}).get("measuregrps", []):
                    date_ts = series.get("date")
                    if not date_ts:
                        continue
                    date_str = datetime.fromtimestamp(date_ts, tz=timezone.utc).strftime("%Y-%m-%d")

                    measurements = {}
                    for m in series.get("measurement", []):
                        cat = m.get("type", {}).get("category", -1)
                        unit = m.get("type", {}).get("unit", 1)
                        value = m.get("value", 0)

                        # 重量单位：1=0.1kg, 2=0.01kg
                        if cat == 250:  # Weight
                            weight_kg = value / 10 if unit == 1 else value / 100
                            measurements["weight_kg"] = round(weight_kg, 1)
                        elif cat == 251:  # Body Fat
                            measurements["body_fat_pct"] = round(value / 10, 1)
                        elif cat == 524:  # Systolic BP
                            measurements["systolic"] = value
                        elif cat == 3026:  # Diastolic BP
                            measurements["diastolic"] = value
                        elif cat == 3025:  # Heart Rate
                            measurements["heart_rate"] = value

                    if measurements:
                        measurements["date"] = date_str
                        measurements["source"] = "withings"
                        items.append(measurements)

                return {
                    "items_count": len(items),
                    "items": items,
                    "message": f"Fetched {len(items)} measurements from Withings ({days} days)",
                }

        except httpx.HTTPStatusError as exc:
            logger.error(f"Withings API HTTP error: {exc.response.status_code}")
            return {
                "items_count": 0,
                "items": [],
                "error": f"Withings API HTTP {exc.response.status_code}",
                "message": "Withings API 请求失败",
            }
        except Exception as exc:
            logger.error(f"Withings API error: {exc}")
            return {
                "items_count": 0,
                "items": [],
                "error": str(exc),
                "message": "Withings API 异常",
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
