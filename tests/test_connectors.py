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
async def test_huawei_sync_mock():
    """测试华为健康数据同步(mock)"""
    import app.connectors.huawei_health
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
async def test_withings_sync():
    """测试 Withings 数据同步"""
    import app.connectors.withings
    connector = ConnectorRegistry.get("withings")
    result = await connector.sync_data("fake_token", "user456")
    assert result["items_count"] > 0
    # 应该包含体重和血压
    loinc_codes = [o["loinc_code"] for o in result["observations"]]
    assert "29463-7" in loinc_codes  # 体重
    assert "8480-6" in loinc_codes   # 收缩压
