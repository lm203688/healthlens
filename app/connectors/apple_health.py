"""Apple Health 数据连接器
Phase 1: 支持 HealthKit 导出的 XML 文件解析
Phase 2: 通过 iOS App + HealthKit Framework 实时同步

Apple HealthKit 不支持服务器端 OAuth2，必须通过 iOS App 中转。
用户从 iPhone 健康App 导出健康数据，上传 XML 文件到 HealthLens。
"""
from datetime import datetime, timezone
from loguru import logger
from app.connectors.base import BaseConnector, ConnectorRegistry


class AppleHealthConnector(BaseConnector):
    """Apple Health 连接器 - XML 导入模式"""

    SOURCE_TYPE = "apple_health"
    DISPLAY_NAME = "Apple健康"

    async def get_auth_url(self, state: str) -> str:
        raise NotImplementedError("Apple HealthKit 不支持服务器端 OAuth2，请通过 iOS App 导出 XML")

    async def exchange_token(self, code: str) -> dict:
        raise NotImplementedError("Apple HealthKit 不支持服务器端 OAuth2")

    async def fetch_health_data(self, access_token: str, days: int = 7) -> dict:
        raise NotImplementedError("请通过 upload_apple_health_xml 上传 XML 文件")

    async def parse_health_xml(self, xml_content: bytes) -> dict:
        """解析 Apple Health 导出的 XML 文件"""
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            return {"error": f"XML 解析失败: {e}", "items_count": 0}

        items = []
        for record in root.iter("Record"):
            record_type = record.get("type", "")
            value = record.get("value", "")
            start_date = record.get("startDate", "")
            source = record.get("sourceName", "")

            loinc_map = {
                "HKQuantityTypeIdentifierStepCount": ("90536-5", "步数(Steps)", "步"),
                "HKQuantityTypeIdentifierHeartRate": ("8867-4", "心率(Heart Rate)", "bpm"),
                "HKQuantityTypeIdentifierBloodPressureSystolic": ("8480-6", "收缩压(Systolic)", "mmHg"),
                "HKQuantityTypeIdentifierBloodPressureDiastolic": ("8462-4", "舒张压(Diastolic)", "mmHg"),
                "HKQuantityTypeIdentifierBodyMass": ("29463-7", "体重(Body Mass)", "kg"),
                "HKQuantityTypeIdentifierHeight": ("8302-2", "身高(Height)", "m"),
                "HKQuantityTypeIdentifierSleepAnalysis": ("93832-4", "睡眠(Sleep)", "h"),
                "HKQuantityTypeIdentifierActiveEnergyBurned": ("41981-2", "活动能量(Active Energy)", "kcal"),
                "HKQuantityTypeIdentifierDistanceWalkingRunning": ("41953-1", "步行跑步距离", "km"),
                "HKQuantityTypeIdentifierFlightsClimbed": ("90536-5", "爬楼层数", "层"),
            }

            if record_type in loinc_map:
                loinc_code, loinc_name, unit = loinc_map[record_type]
                try:
                    value_numeric = float(value) if record_type != "HKCategoryTypeIdentifierSleepAnalysis" else None
                except (ValueError, TypeError):
                    value_numeric = None

                items.append({
                    "loinc_code": loinc_code,
                    "loinc_name": loinc_name,
                    "value_numeric": value_numeric,
                    "value_string": value if value_numeric is None else None,
                    "value_unit": unit,
                    "source": "apple_health",
                    "recorded_at": start_date,
                })

        logger.info(f"Apple Health XML parsed: {len(items)} records")
        return {
            "items_count": len(items),
            "items": items,
            "message": f"Parsed {len(items)} health records from Apple Health XML",
        }

    async def sync_data(self, access_token: str, user_id: str, since: datetime | None = None) -> dict:
        """Apple Health 通过 XML 文件导入，不支持实时同步"""
        return {
            "items_count": 0,
            "message": "Apple Health requires XML file upload. Use parse_health_xml() instead.",
        }


ConnectorRegistry.register("apple_health", AppleHealthConnector)
