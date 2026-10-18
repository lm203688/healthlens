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
        """拉取华为健康数据（真实 API）。

        S1-5 反骨架化：缺凭据时诚实报错，绝不返回 mock。
        上一版 Phase 1 曾以 `huawei_health_mock` 生成数据，违反项目
        「骨架未接线时必须 fail-loud」原则——已移除。
        """
        import httpx

        if not self.client_id or not self.client_secret:
            return {
                "items_count": 0,
                "items": [],
                "error": "华为健康未配置：请在环境变量设置 HUAWEI_HEALTH_CLIENT_ID 和 HUAWEI_HEALTH_CLIENT_SECRET",
                "message": "连接器不可用——需先配置 OAuth2 凭据",
            }
        if not access_token:
            return {
                "items_count": 0,
                "items": [],
                "error": "缺少 access_token",
                "message": "请引导用户完成 OAuth2 授权后重试",
            }

        logger.info(f"Fetching Huawei Health data for {days} days (real API)")

        now = datetime.now(timezone.utc)
        end = now.isoformat()
        start = (now - timedelta(days=days)).isoformat()

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.DATA_URL}/activity/query",
                    json={
                        "query": {
                            "start_time": start,
                            "end_time": end,
                            "types": ["STEPS", "HEART_RATE", "SLEEP"],
                            "aggregation": "daily",
                        }
                    },
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            # 华为健康 v1 返回 { data: { activities: [...] } } 结构
            activities = (data.get("data") or {}).get("activities") or data.get("data") or []
            items = []
            for act in activities:
                items.append({
                    "date": act.get("date") or act.get("start_time", "")[:10],
                    "steps": act.get("steps", 0),
                    "calories": act.get("calories", 0),
                    "heart_rate_avg": act.get("heart_rate_avg", 0),
                    "heart_rate_max": act.get("heart_rate_max", 0),
                    "sleep_hours": act.get("sleep_hours", 0),
                    "weight_kg": act.get("weight_kg", 0),
                    "source": "huawei_health",
                })

            return {
                "items_count": len(items),
                "items": items,
                "message": f"Fetched {len(items)} records from Huawei Health ({days} days)",
            }
        except httpx.HTTPStatusError as exc:
            logger.error(f"Huawei Health API HTTP error: {exc.response.status_code}")
            return {
                "items_count": 0,
                "items": [],
                "error": f"Huawei Health API HTTP {exc.response.status_code}",
                "message": "华为健康 API 请求失败",
            }
        except Exception as exc:
            logger.error(f"Huawei Health API error: {exc}")
            return {
                "items_count": 0,
                "items": [],
                "error": str(exc),
                "message": "华为健康 API 异常",
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