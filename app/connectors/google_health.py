"""Google Health Connect / Google Fit 数据连接器
支持 Android Health Connect JSON 导出格式解析。

Health Connect 是 Android 13+ 的统一健康数据存储层，替代 Google Fit。
用户可从 Android 健康 App 导出数据为 JSON 格式，上传到 HealthLens。
"""
from datetime import datetime, timezone
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class GoogleHealthConnector(BaseConnector):
    """Google Health Connect / Google Fit 连接器 - JSON 导入模式"""

    SOURCE_TYPE = "google_health"
    DISPLAY_NAME = "Google Health"

    async def get_auth_url(self, state: str) -> str:
        raise NotImplementedError("Google Health Connect 不支持服务器端 OAuth2，请通过 Android 导出 JSON")

    async def exchange_token(self, code: str) -> dict:
        raise NotImplementedError("Google Health Connect 不支持服务器端 OAuth2")

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        raise NotImplementedError("请通过 upload_google_health_json 上传 JSON 文件")

    async def parse_health_json(self, json_content: bytes) -> dict:
        """解析 Google Health Connect / Google Fit 导出的 JSON 文件"""
        import json

        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            return {"error": f"JSON 解析失败: {e}", "items_count": 0}

        items = []

        # Health Connect 导出格式
        if "records" in data:
            for record in data["records"]:
                item = self._parse_health_connect_record(record)
                if item:
                    items.append(item)
        # Google Fit 导出格式
        elif "dataset" in data:
            for dataset in data["dataset"]:
                for point in dataset.get("point", []):
                    item = self._parse_google_fit_point(point)
                    if item:
                        items.append(item)
        # 扁平列表格式
        elif isinstance(data, list):
            for record in data:
                item = self._parse_health_connect_record(record)
                if item:
                    items.append(item)
        else:
            # 尝试直接解析为单条记录
            item = self._parse_health_connect_record(data)
            if item:
                items.append(item)

        logger.info(f"Google Health JSON parsed: {len(items)} records")
        return {
            "items_count": len(items),
            "items": items,
            "message": f"Parsed {len(items)} health records from Google Health Connect",
        }

    def _parse_health_connect_record(self, record: dict) -> dict | None:
        """解析 Health Connect 单条记录"""
        record_type = record.get("type", "")
        timestamp = record.get("startTimeNanos", "") or record.get("time", "")

        # 数值字段
        value = record.get("floatVal") or record.get("value") or record.get("count")

        loinc_map = {
            "org.healthconnect.SleepSessionRecord": ("93832-4", "睡眠(Sleep)", "h"),
            "org.healthconnect.HeartRateRecord": ("8867-4", "心率(Heart Rate)", "bpm"),
            "org.healthconnect.TotalStepsRecord": ("90536-5", "步数(Steps)", "步"),
            "org.healthconnect.ActiveTimeRecord": ("41981-2", "活动能量(Active Energy)", "kcal"),
            "org.healthconnect.DistanceRecord": ("41953-1", "步行跑步距离", "km"),
            "org.healthconnect.WeightRecord": ("29463-7", "体重(Body Mass)", "kg"),
            "org.healthconnect.HeightRecord": ("8302-2", "身高(Height)", "m"),
            "org.healthconnect.BloodPressureRecord": ("8480-6", "血压(Blood Pressure)", "mmHg"),
            "org.healthconnect.BloodGlucoseRecord": ("2339-6", "血糖(Blood Glucose)", "mg/dL"),
            "org.healthconnect.HeartRateBpmRecord": ("8867-4", "心率(Heart Rate)", "bpm"),
            "org.healthconnect.ExerciseSessionRecord": ("41981-2", "运动(Motion)", "min"),
        }

        if record_type not in loinc_map:
            return None

        loinc_code, loinc_name, unit = loinc_map[record_type]

        # 解析时间
        if isinstance(timestamp, (int, float)):
            start_date = datetime.fromtimestamp(timestamp / 1e9 if timestamp > 1e12 else timestamp, tz=timezone.utc)
        else:
            start_date = timestamp

        return {
            "loinc_code": loinc_code,
            "loinc_name": loinc_name,
            "value_numeric": float(value) if value is not None else None,
            "value_string": str(value) if value is not None and isinstance(value, (str, int, float)) else None,
            "value_unit": unit,
            "source": "google_health",
            "recorded_at": start_date.isoformat() if isinstance(start_date, datetime) else str(start_date),
        }

    def _parse_google_fit_point(self, point: dict) -> dict | None:
        """解析 Google Fit 数据点"""
        dt_str = point.get("deviceTimeMillis", "")
        value = point.get("value", [])

        # Google Fit 使用 data type identifier
        type_map = {
            "com.google.heart_rate.bpm": ("8867-4", "心率(Heart Rate)", "bpm"),
            "com.google.step_count.delta": ("90536-5", "步数(Steps)", "步"),
            "com.google.calorie.expended": ("41981-2", "活动能量(Active Energy)", "kcal"),
            "com.google.distance.distance_delta": ("41953-1", "步行跑步距离", "km"),
            "com.google.weight.weight": ("29463-7", "体重(Body Mass)", "kg"),
            "com.google.blood_glucose.concentration": ("2339-6", "血糖(Blood Glucose)", "mg/dL"),
        }

        data_type = point.get("dataType", "")
        if data_type not in type_map:
            return None

        loinc_code, loinc_name, unit = type_map[data_type]

        # 解析值
        if isinstance(value, list) and len(value) > 0:
            val = value[0].get("fpVal") or value[0].get("intVal")
        else:
            val = value

        # 解析时间
        if dt_str:
            ts = int(dt_str) / 1000  # ms to s
            start_date = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            start_date = datetime.now(timezone.utc)

        return {
            "loinc_code": loinc_code,
            "loinc_name": loinc_name,
            "value_numeric": float(val) if val is not None else None,
            "value_unit": unit,
            "source": "google_health",
            "recorded_at": start_date.isoformat(),
        }
