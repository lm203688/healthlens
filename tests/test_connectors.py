"""数据连接器测试"""
import pytest
from app.connectors.base import ConnectorRegistry


def test_registry_has_all_connectors():
    """测试所有连接器已注册"""
    # 导入所有连接器模块触发注册
    import app.connectors.huawei_health
    import app.connectors.apple_health
    import app.connectors.withings
    import app.connectors.xiaomi_health
    import app.connectors.hospital_lis

    sources = ConnectorRegistry.available_sources()
    assert "huawei_health" in sources
    assert "apple_health" in sources
    assert "withings" in sources
    assert "xiaomi_health" in sources
    assert "hospital_lis" in sources


def test_huawei_health_connector():
    """测试华为健康连接器"""
    import app.connectors.huawei_health
    connector = ConnectorRegistry.get("huawei_health")
    assert connector is not None
    assert connector.SOURCE_TYPE == "huawei_health"
    assert connector.DISPLAY_NAME == "华为健康"


@pytest.mark.asyncio
async def test_huawei_sync_mock(monkeypatch):
    """测试华为健康数据同步

    S1-5（2026-10-15）：连接器已改为反骨架化 fail-loud 模式，
    缺凭据时诚实报错，绝不返回 mock。测试通过 monkeypatch
    fetch_health_data 注入数据来验证 sync_data 的格式转换逻辑，
    与 Withings 测试保持同一策略。
    """
    import app.connectors.huawei_health
    from app.connectors.huawei_health import HuaweiHealthConnector

    async def _mock_fetch(self, access_token, days=7):
        return {
            "items_count": 1,
            "items": [{
                "date": "2026-10-15",
                "steps": 8500,
                "calories": 1800,
                "heart_rate_avg": 72,
                "source": "huawei_health",
            }],
            "message": "mock data for test",
        }

    monkeypatch.setattr(HuaweiHealthConnector, "fetch_health_data", _mock_fetch)

    connector = ConnectorRegistry.get("huawei_health")
    result = await connector.sync_data("fake_token", "user123")
    assert result["items_count"] > 0
    assert "observations" in result


@pytest.mark.asyncio
async def test_apple_health_xml_parse():
    """测试 Apple Health XML 解析"""
    import app.connectors.apple_health
    connector = ConnectorRegistry.get("apple_health")
    
    xml_content = b'''<?xml version="1.0"?>
    <HealthData>
      <Record type="HKQuantityTypeIdentifierStepCount" value="8500" startDate="2026-07-17 10:00:00 +0800" sourceName="iPhone"/>
      <Record type="HKQuantityTypeIdentifierHeartRate" value="72" startDate="2026-07-17 10:05:00 +0800" sourceName="Apple Watch"/>
    </HealthData>'''
    
    result = await connector.parse_health_xml(xml_content)
    assert result["items_count"] == 2
    assert result["items"][0]["loinc_code"] == "90536-5"  # 步数
    assert result["items"][1]["loinc_code"] == "8867-4"   # 心率


@pytest.mark.asyncio
async def test_withings_sync(monkeypatch):
    """测试 Withings 数据同步（mock fetch_health_data，避免真实 API 依赖）

    S0-3（2026-10-12）：Withings 连接器已改为 P0-7 真实 API 模式（缺凭据诚实报错），
    测试通过 monkeypatch fetch_health_data 注入模拟数据来验证 sync_data 的格式转换逻辑。
    """
    import app.connectors.withings
    from app.connectors.withings import WithingsConnector

    async def _mock_fetch(self, access_token, days=7):
        return {
            "items_count": 1,
            "items": [{
                "weight_kg": 72.5,
                "systolic": 120,
                "diastolic": 80,
                "date": "2026-10-12",
                "source": "withings_mock",
            }],
            "message": "mock data for test",
        }

    monkeypatch.setattr(WithingsConnector, "fetch_health_data", _mock_fetch)

    connector = ConnectorRegistry.get("withings")
    result = await connector.sync_data("fake_token", "user456")
    assert result["items_count"] > 0
    loinc_codes = [o["loinc_code"] for o in result["observations"]]
    assert "29463-7" in loinc_codes  # 体重
    assert "8480-6" in loinc_codes   # 收缩压


@pytest.mark.asyncio
async def test_google_health_json_parse():
    """测试 Google Health Connect JSON 解析"""
    import app.connectors.google_health
    connector = ConnectorRegistry.get("google_health")
    
    json_content = b'''{
        "records": [
            {"type": "org.healthconnect.TotalStepsRecord", "count": 8500, "startTimeNanos": 1721184000000000000},
            {"type": "org.healthconnect.HeartRateRecord", "floatVal": 72, "startTimeNanos": 1721184300000000000}
        ]
    }'''
    
    result = await connector.parse_health_json(json_content)
    assert result["items_count"] == 2
    assert result["items"][0]["loinc_code"] == "90536-5"  # 步数
    assert result["items"][1]["loinc_code"] == "8867-4"   # 心率


def test_google_health_connector_registered():
    """测试 Google Health 连接器已注册"""
    sources = ConnectorRegistry.available_sources()
    assert "google_health" in sources
    connector = ConnectorRegistry.get("google_health")
    assert connector is not None
    assert connector.SOURCE_TYPE == "google_health"
