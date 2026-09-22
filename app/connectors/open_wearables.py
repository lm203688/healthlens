"""Open Wearables 连接器
统一接入 14 个可穿戴设备（Garmin/Oura/WHOOP/Polar/Suunto/Strava/Apple/Samsung/Fitbit/Ultrahuman/Withings/Google Health/...）

架构：
  HealthLens → Open Wearables API → 各 Provider API
  - OAuth 流程由 OW 处理
  - Token 刷新由 OW 自动管理
  - 数据格式由 OW 统一归一化
  - 本连接器负责 OW schema → HealthLens HealthObservation / SleepRecord 映射

API 文档: https://openwearables.io/docs
GitHub: https://github.com/the-momentum/open-wearables (MIT)
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

import httpx
from loguru import logger

from app.connectors.base import BaseConnector, ConnectorRegistry
from app.config import settings


class OpenWearablesConnector(BaseConnector):
    """Open Wearables 连接器 - 统一 14 设备接入"""

    SOURCE_TYPE = "open_wearables"
    DISPLAY_NAME = "Open Wearables (14 devices)"

    # OW API 端点
    SUMMARIES_SLEEP = "/api/v1/users/{user_id}/summaries/sleep"
    SUMMARIES_ACTIVITY = "/api/v1/users/{user_id}/summaries/activity"
    SUMMARIES_BODY = "/api/v1/users/{user_id}/summaries/body"
    SUMMARIES_RECOVERY = "/api/v1/users/{user_id}/summaries/recovery"
    EVENTS_WORKOUTS = "/api/v1/users/{user_id}/events/workouts"
    EVENTS_SLEEP = "/api/v1/users/{user_id}/events/sleep"
    TIMESERIES = "/api/v1/users/{user_id}/timeseries"
    USERS_LIST = "/api/v1/users"

    def __init__(self):
        self.api_url = getattr(settings, "OPEN_WEARABLES_API_URL", "http://localhost:8001")
        self.api_key = getattr(settings, "OPEN_WEARABLES_API_KEY", "")
        self._http = None

    # ------------------------------------------------------------------
    # HTTP 客户端管理
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.api_url,
                timeout=30.0,
                headers={
                    "X-Open-Wearables-API-Key": self.api_key,
                    "Accept": "application/json",
                },
            )
        return self._http

    async def close(self):
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # OW API 调用
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """调用 OW REST API"""
        client = await self._get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _list_users(self, search: str = "", limit: int = 50) -> list[dict]:
        """查询 OW 用户列表"""
        params = {"limit": limit}
        if search:
            params["search"] = search
        data = await self._get(self.USERS_LIST, params)
        return data.get("users", data.get("data", []))

    async def _find_ow_user(self, hl_user_id: str) -> str | None:
        """通过 HL 用户 ID 映射找 OW 用户 ID
        映射策略：先查 DataConnection.config 里的 ow_user_id，
        如果没找到则尝试用 email 匹配。
        """
        # 简单策略：用 HL user_id 做搜索关键词
        try:
            users = await self._list_users(search=hl_user_id, limit=1)
            if users:
                return users[0].get("id")
        except Exception as e:
            logger.warning(f"OW user lookup by id failed: {e}")
        return None

    # ------------------------------------------------------------------
    # 数据拉取
    # ------------------------------------------------------------------

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        """拉取 OW 归一化数据

        access_token: 实际是 OW 的用户 ID（不是 OAuth token）
        """
        ow_user_id = access_token
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        params = {"start_date": start_date, "end_date": end_date}

        results: dict[str, Any] = {"items_count": 0, "items": []}

        # 1. 睡眠摘要
        try:
            sleep_data = await self._get(
                self.SUMMARIES_SLEEP.format(user_id=ow_user_id), params
            )
            sleep_records = sleep_data.get("records", sleep_data.get("data", []))
            results["sleep_summaries"] = sleep_records
            results["items_count"] += len(sleep_records)
        except Exception as e:
            logger.warning(f"OW sleep summaries fetch failed: {e}")

        # 2. 活动摘要
        try:
            activity_data = await self._get(
                self.SUMMARIES_ACTIVITY.format(user_id=ow_user_id), params
            )
            activity_records = activity_data.get("records", activity_data.get("data", []))
            results["activity_summaries"] = activity_records
            results["items_count"] += len(activity_records)
        except Exception as e:
            logger.warning(f"OW activity summaries fetch failed: {e}")

        # 3. 身体数据摘要
        try:
            body_data = await self._get(
                self.SUMMARIES_BODY.format(user_id=ow_user_id), params
            )
            body_records = body_data.get("records", body_data.get("data", []))
            results["body_summaries"] = body_records
            results["items_count"] += len(body_records)
        except Exception as e:
            logger.warning(f"OW body summaries fetch failed: {e}")

        # 4. 恢复数据摘要
        try:
            recovery_data = await self._get(
                self.SUMMARIES_RECOVERY.format(user_id=ow_user_id), params
            )
            recovery_records = recovery_data.get("records", recovery_data.get("data", []))
            results["recovery_summaries"] = recovery_records
            results["items_count"] += len(recovery_records)
        except Exception as e:
            logger.warning(f"OW recovery summaries fetch failed: {e}")

        # 5. 运动事件
        try:
            workouts_data = await self._get(
                self.EVENTS_WORKOUTS.format(user_id=ow_user_id), params
            )
            workout_events = workouts_data.get("records", workouts_data.get("data", []))
            results["workout_events"] = workout_events
            results["items_count"] += len(workout_events)
        except Exception as e:
            logger.warning(f"OW workouts fetch failed: {e}")

        # 6. 睡眠事件（详细阶段数据）
        try:
            sleep_events_data = await self._get(
                self.EVENTS_SLEEP.format(user_id=ow_user_id), params
            )
            sleep_events = sleep_events_data.get("records", sleep_events_data.get("data", []))
            results["sleep_events"] = sleep_events
            results["items_count"] += len(sleep_events)
        except Exception as e:
            logger.warning(f"OW sleep events fetch failed: {e}")

        # 7. 时序数据（HRV / SpO2 / 体重等）
        try:
            ts_data = await self._get(
                self.TIMESERIES.format(user_id=ow_user_id), params
            )
            ts_records = ts_data.get("records", ts_data.get("data", []))
            results["timeseries"] = ts_records
            results["items_count"] += len(ts_records)
        except Exception as e:
            logger.warning(f"OW timeseries fetch failed: {e}")

        results["message"] = f"Fetched {days} days from Open Wearables, {results['items_count']} total records"
        return results

    # ------------------------------------------------------------------
    # 同步到 HealthLens 格式
    # ------------------------------------------------------------------

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        """同步 OW 数据到 HealthLens HealthObservation / SleepRecord 格式

        access_token: OW 用户 ID
        """
        days = 7
        if since:
            delta = (datetime.now(timezone.utc) - since).days
            days = min(max(delta, 1), 30)

        data = await self.fetch_health_data(access_token, days)

        observations: list[dict] = []
        sleep_records: list[dict] = []

        # === 睡眠摘要 → SleepRecord ===
        for rec in data.get("sleep_summaries", []):
            sleep_rec = self._map_sleep_summary(rec, user_id)
            if sleep_rec:
                sleep_records.append(sleep_rec)

        # === 睡眠事件（阶段数据）→ SleepRecord 增强 ===
        for rec in data.get("sleep_events", []):
            sleep_rec = self._map_sleep_event(rec, user_id)
            if sleep_rec:
                sleep_records.append(sleep_rec)

        # === 活动摘要 → HealthObservation ===
        for rec in data.get("activity_summaries", []):
            observations.extend(self._map_activity_summary(rec, user_id))

        # === 身体数据 → HealthObservation ===
        for rec in data.get("body_summaries", []):
            observations.extend(self._map_body_summary(rec, user_id))

        # === 运动事件 → HealthObservation ===
        for rec in data.get("workout_events", []):
            observations.extend(self._map_workout_event(rec, user_id))

        # === 时序数据 → HealthObservation ===
        for rec in data.get("timeseries", []):
            observations.extend(self._map_timeseries(rec, user_id))

        # === 恢复数据 → HealthObservation ===
        for rec in data.get("recovery_summaries", []):
            observations.extend(self._map_recovery_summary(rec, user_id))

        return {
            "items_count": len(observations) + len(sleep_records),
            "observations": observations,
            "sleep_records": sleep_records,
            "message": f"Synced {days} days: {len(observations)} observations + {len(sleep_records)} sleep records",
        }

    # ------------------------------------------------------------------
    # 数据映射函数：OW Schema → HealthLens LOINC
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(value: str | datetime | None) -> datetime | None:
        """解析 OW 日期格式"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _map_sleep_summary(self, rec: dict, hl_user_id: str) -> dict | None:
        """OW 睡眠摘要 → HealthLens SleepRecord"""
        date_str = rec.get("date") or rec.get("sleep_date") or rec.get("day", "")
        if not date_str:
            return None

        try:
            sleep_date = date_str[:10]  # YYYY-MM-DD
        except (TypeError, ValueError):
            return None

        return {
            "user_id": hl_user_id,
            "sleep_date": sleep_date,
            "total_duration_min": self._to_float(rec.get("total_duration_min") or rec.get("total_duration") or rec.get("duration_minutes")),
            "deep_sleep_min": self._to_float(rec.get("deep_sleep_min") or rec.get("deep_sleep")),
            "light_sleep_min": self._to_float(rec.get("light_sleep_min") or rec.get("light_sleep")),
            "rem_sleep_min": self._to_float(rec.get("rem_sleep_min") or rec.get("rem_sleep")),
            "awake_min": self._to_float(rec.get("awake_min") or rec.get("awake")),
            "sleep_efficiency": self._to_float(rec.get("sleep_efficiency") or rec.get("efficiency")),
            "hrv_avg": self._to_float(rec.get("hrv_avg") or rec.get("hrv")),
            "bedtime": self._extract_time(rec.get("bedtime") or rec.get("sleep_start")),
            "wake_time": self._extract_time(rec.get("wake_time") or rec.get("sleep_end")),
            "source": "open_wearables",
            "raw_data": rec,
        }

    def _map_sleep_event(self, rec: dict, hl_user_id: str) -> dict | None:
        """OW 睡眠事件 → SleepRecord（补充阶段数据）"""
        start = self._parse_date(rec.get("start") or rec.get("start_time"))
        if not start:
            return None

        return {
            "user_id": hl_user_id,
            "sleep_date": start.strftime("%Y-%m-%d"),
            "total_duration_min": self._to_float(
                rec.get("duration_min") or rec.get("duration") or rec.get("duration_minutes")
            ),
            "deep_sleep_min": self._to_float(rec.get("deep_duration_min") or rec.get("deep_duration")),
            "rem_sleep_min": self._to_float(rec.get("rem_duration_min") or rec.get("rem_duration")),
            "sleep_efficiency": self._to_float(rec.get("efficiency")),
            "source": "open_wearables",
            "raw_data": rec,
        }

    def _map_activity_summary(self, rec: dict, hl_user_id: str) -> list[dict]:
        """OW 活动摘要 → HealthObservation 列表"""
        date = self._to_date_str(rec.get("date") or rec.get("day"))
        if not date:
            return []

        observed_at = f"{date}T12:00:00"
        obs = []

        # 步数
        steps = self._to_float(rec.get("steps"))
        if steps is not None:
            obs.append({
                "loinc_code": "90536-5", "loinc_name": "步数(Steps)",
                "value_numeric": steps, "value_unit": "步",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 卡路里
        calories = self._to_float(rec.get("calories") or rec.get("active_energy_kcal") or rec.get("active_energy"))
        if calories is not None:
            obs.append({
                "loinc_code": "41981-2", "loinc_name": "活动能量(Active Energy)",
                "value_numeric": calories, "value_unit": "kcal",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 平均心率
        hr_avg = self._to_float(rec.get("heart_rate_avg") or rec.get("average_heart_rate"))
        if hr_avg is not None:
            obs.append({
                "loinc_code": "8867-4", "loinc_name": "心率(Heart Rate)",
                "value_numeric": hr_avg, "value_unit": "bpm",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 最大心率
        hr_max = self._to_float(rec.get("heart_rate_max") or rec.get("max_heart_rate"))
        if hr_max is not None:
            obs.append({
                "loinc_code": "8867-4", "loinc_name": "心率最大(Heart Rate Max)",
                "value_numeric": hr_max, "value_unit": "bpm",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 距离
        distance = self._to_float(rec.get("distance") or rec.get("distance_m"))
        if distance is not None:
            obs.append({
                "loinc_code": "41953-1", "loinc_name": "步行跑步距离",
                "value_numeric": distance / 1000, "value_unit": "km",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 强度分钟
        intensity_min = self._to_float(rec.get("intensity_minutes") or rec.get("active_minutes"))
        if intensity_min is not None:
            obs.append({
                "loinc_code": "intensity_minutes", "loinc_name": "强度运动分钟数",
                "value_numeric": intensity_min, "value_unit": "min",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        return obs

    def _map_body_summary(self, rec: dict, hl_user_id: str) -> list[dict]:
        """OW 身体数据 → HealthObservation"""
        date = self._to_date_str(rec.get("date") or rec.get("day"))
        if not date:
            return []

        observed_at = f"{date}T12:00:00"
        obs = []

        # 体重
        weight = self._to_float(rec.get("weight") or rec.get("weight_kg"))
        if weight is not None:
            obs.append({
                "loinc_code": "29463-7", "loinc_name": "体重(Body Mass)",
                "value_numeric": weight, "value_unit": "kg",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 体脂率
        fat_pct = self._to_float(rec.get("body_fat_pct") or rec.get("fat_percentage"))
        if fat_pct is not None:
            obs.append({
                "loinc_code": "body_fat_pct", "loinc_name": "体脂率(Body Fat %)",
                "value_numeric": fat_pct, "value_unit": "%",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 血压
        systolic = self._to_float(rec.get("systolic") or rec.get("blood_pressure_systolic"))
        diastolic = self._to_float(rec.get("diastolic") or rec.get("blood_pressure_diastolic"))
        if systolic is not None:
            obs.append({
                "loinc_code": "8480-6", "loinc_name": "收缩压(Systolic)",
                "value_numeric": systolic, "value_unit": "mmHg",
                "source": "open_wearables", "recorded_at": observed_at,
            })
        if diastolic is not None:
            obs.append({
                "loinc_code": "8462-4", "loinc_name": "舒张压(Diastolic)",
                "value_numeric": diastolic, "value_unit": "mmHg",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        return obs

    def _map_workout_event(self, rec: dict, hl_user_id: str) -> list[dict]:
        """OW 运动事件 → HealthObservation"""
        start = self._parse_date(rec.get("start") or rec.get("start_time"))
        if not start:
            return []

        observed_at = start.isoformat()
        obs = []

        # 运动时长
        duration = self._to_float(rec.get("duration_min") or rec.get("duration") or rec.get("duration_minutes"))
        if duration is not None:
            obs.append({
                "loinc_code": "workout_duration", "loinc_name": "运动时长",
                "value_numeric": duration, "value_unit": "min",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 运动类型
        sport = rec.get("sport") or rec.get("workout_type") or rec.get("activity_type")
        if sport:
            obs.append({
                "loinc_code": "workout_type", "loinc_name": "运动类型",
                "value_string": str(sport), "value_numeric": None, "value_unit": None,
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 卡路里
        calories = self._to_float(rec.get("calories") or rec.get("active_energy_kcal"))
        if calories is not None:
            obs.append({
                "loinc_code": "41981-2", "loinc_name": "运动能量(Workout Energy)",
                "value_numeric": calories, "value_unit": "kcal",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        return obs

    def _map_timeseries(self, rec: dict, hl_user_id: str) -> list[dict]:
        """OW 时序数据 → HealthObservation"""
        ts = self._parse_date(rec.get("timestamp") or rec.get("time") or rec.get("recorded_at"))
        if not ts:
            return []

        observed_at = ts.isoformat()
        obs = []

        # 心率
        hr = self._to_float(rec.get("heart_rate") or rec.get("hr"))
        if hr is not None:
            obs.append({
                "loinc_code": "8867-4", "loinc_name": "心率(Heart Rate)",
                "value_numeric": hr, "value_unit": "bpm",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # HRV
        hrv = self._to_float(rec.get("hrv") or rec.get("hrv_rmssd") or rec.get("hrv_ms"))
        if hrv is not None:
            obs.append({
                "loinc_code": "hrv", "loinc_name": "心率变异(HRV)",
                "value_numeric": hrv, "value_unit": "ms",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # SpO2
        spo2 = self._to_float(rec.get("spo2") or rec.get("blood_oxygen"))
        if spo2 is not None:
            obs.append({
                "loinc_code": "59408-5", "loinc_name": "血氧饱和度(SpO2)",
                "value_numeric": spo2, "value_unit": "%",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 呼吸率
        rr = self._to_float(rec.get("respiratory_rate") or rec.get("rr"))
        if rr is not None:
            obs.append({
                "loinc_code": "9279-3", "loinc_name": "呼吸率(Respiratory Rate)",
                "value_numeric": rr, "value_unit": "次/分",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 血糖
        glucose = self._to_float(rec.get("glucose") or rec.get("blood_glucose"))
        if glucose is not None:
            obs.append({
                "loinc_code": "glucose", "loinc_name": "血糖(Blood Glucose)",
                "value_numeric": glucose, "value_unit": "mmol/L",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 步数
        steps = self._to_float(rec.get("steps"))
        if steps is not None:
            obs.append({
                "loinc_code": "90536-5", "loinc_name": "步数(Steps)",
                "value_numeric": steps, "value_unit": "步",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        return obs

    def _map_recovery_summary(self, rec: dict, hl_user_id: str) -> list[dict]:
        """OW 恢复数据 → HealthObservation"""
        date = self._to_date_str(rec.get("date") or rec.get("day"))
        if not date:
            return []

        observed_at = f"{date}T12:00:00"
        obs = []

        # 恢复评分
        recovery_score = self._to_float(rec.get("recovery_score") or rec.get("score"))
        if recovery_score is not None:
            obs.append({
                "loinc_code": "recovery_score", "loinc_name": "恢复评分(Recovery Score)",
                "value_numeric": recovery_score, "value_unit": "/100",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 压力评分
        stress_score = self._to_float(rec.get("stress_score"))
        if stress_score is not None:
            obs.append({
                "loinc_code": "stress_score", "loinc_name": "压力评分(Stress Score)",
                "value_numeric": stress_score, "value_unit": "/100",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        # 睡眠评分
        sleep_score = self._to_float(rec.get("sleep_score"))
        if sleep_score is not None:
            obs.append({
                "loinc_code": "sleep_score", "loinc_name": "睡眠评分(Sleep Score)",
                "value_numeric": sleep_score, "value_unit": "/100",
                "source": "open_wearables", "recorded_at": observed_at,
            })

        return obs

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _to_float(value: Any) -> float | None:
        """安全转 float"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_date_str(value: Any) -> str | None:
        """提取 YYYY-MM-DD"""
        if not value:
            return None
        s = str(value)
        return s[:10] if len(s) >= 10 else None

    @staticmethod
    def _extract_time(value: Any) -> str | None:
        """从 ISO datetime 提取 HH:MM"""
        if not value:
            return None
        s = str(value)
        if "T" in s:
            parts = s.split("T")
            time_part = parts[1]
            if "+" in time_part:
                time_part = time_part.split("+")[0]
            if "Z" in time_part:
                time_part = time_part.replace("Z", "")
            return time_part[:5]
        return None

    # ------------------------------------------------------------------
    # OAuth（OW 原生支持）
    # ------------------------------------------------------------------

    async def get_auth_url(self, state: str) -> str:
        """获取 OW 支持的 provider 列表 + 授权 URL"""
        # OW 的 OAuth 由前端 widget 或独立 endpoint 处理
        # 这里返回支持列表
        supported = [
            "garmin", "oura", "whoop", "polar", "suunto",
            "strava", "fitbit", "ultrahuman", "withings", "google_health",
        ]
        return f"{self.api_url}/api/v1/providers"

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """检查 OW 服务是否可达"""
        try:
            client = await self._get_client()
            resp = await client.get("/api/v1/health", timeout=5.0)
            resp.raise_for_status()
            return {"status": "ok", "detail": resp.json()}
        except httpx.ConnectError:
            return {"status": "unreachable", "detail": f"Cannot connect to {self.api_url}"}
        except httpx.TimeoutException:
            return {"status": "timeout", "detail": f"Timeout connecting to {self.api_url}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}


ConnectorRegistry.register("open_wearables", OpenWearablesConnector)
