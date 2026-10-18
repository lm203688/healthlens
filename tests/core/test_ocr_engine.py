"""OCR 引擎单元测试 - 仅测试 MockOCR 和 get_ocr_engine 工厂函数"""
import pytest
from app.core.ocr_engine import MockOCREngine, get_ocr_engine, BaseOCREngine


@pytest.mark.asyncio
async def test_mock_ocr_pdf():
    """MockOCR 解析 PDF bytes 应返回体检报告"""
    engine = MockOCREngine()
    pdf_bytes = b"%PDF-1.4 fake pdf content for testing"

    result = await engine.parse(pdf_bytes)

    assert result.raw_text != ""
    assert result.confidence > 0
    assert result.structured_data["report_type"] == "physical_examination"
    assert len(result.structured_data["observations"]) > 0
    # 体检报告应包含血糖 loinc_code "2345-7"
    obs_codes = [o["loinc_code"] for o in result.structured_data["observations"]]
    assert "2345-7" in obs_codes


@pytest.mark.asyncio
async def test_mock_ocr_jpeg():
    """MockOCR 解析 JPEG bytes 应返回血液检查"""
    engine = MockOCREngine()
    # JPEG 文件魔数: \xff\xd8\xff\xe0 (JFIF)
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    result = await engine.parse(jpeg_bytes)

    assert result.raw_text != ""
    assert result.confidence > 0
    assert result.structured_data["report_type"] == "blood_test"
    assert len(result.structured_data["observations"]) > 0


@pytest.mark.asyncio
async def test_mock_ocr_unknown_type():
    """未知文件类型应默认返回体检报告"""
    engine = MockOCREngine()
    unknown_bytes = b"this is some random content without file magic"

    result = await engine.parse(unknown_bytes)

    assert result.structured_data["report_type"] == "physical_examination"


def test_get_ocr_engine_mock():
    """get_ocr_engine('mock') 应返回 MockOCREngine 实例"""
    engine = get_ocr_engine("mock")
    assert isinstance(engine, MockOCREngine)
    assert isinstance(engine, BaseOCREngine)


def test_get_ocr_engine_unknown():
    """未知引擎类型应抛 ValueError"""
    with pytest.raises(ValueError, match="Unknown OCR engine"):
        get_ocr_engine("nonexistent_engine")