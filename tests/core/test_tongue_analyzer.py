"""舌象分析器测试"""
import pytest
from io import BytesIO
from app.core.tcm_tongue_analyzer import TongueAnalyzer


def _make_test_image(r: int = 200, g: int = 150, b: int = 150) -> bytes:
    """生成测试图片"""
    from PIL import Image
    img = Image.new("RGB", (200, 200), (r, g, b))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_analyze_normal_tongue():
    """测试淡红舌分析"""
    analyzer = TongueAnalyzer()
    image_bytes = _make_test_image(r=195, g=155, b=155)
    result = analyzer.analyze(image_bytes)
    assert result.tongue_color in ["淡红", "红"]
    assert result.coating_color in ["薄白", "白"]
    assert result.confidence > 0


def test_analyze_pale_tongue():
    """测试淡白舌分析"""
    analyzer = TongueAnalyzer()
    image_bytes = _make_test_image(r=170, g=170, b=170)
    result = analyzer.analyze(image_bytes)
    assert result.tongue_color in ["淡白", "淡红"]
    assert "syndrome_hint" in result.syndrome_hint or "舌色" in result.syndrome_hint


def test_analyze_raw_metrics():
    """测试颜色指标提取"""
    analyzer = TongueAnalyzer()
    image_bytes = _make_test_image(r=200, g=100, b=100)
    metrics = analyzer.analyze_image_colors(image_bytes)
    assert "r_avg" in metrics
    assert "g_avg" in metrics
    assert "b_avg" in metrics
    assert metrics["r_avg"] > metrics["b_avg"]  # 红色 > 蓝色


@pytest.mark.asyncio
async def test_analyze_async():
    """测试异步分析"""
    analyzer = TongueAnalyzer()
    image_bytes = _make_test_image()
    result = await analyzer.analyze_async(image_bytes)
    assert result.tongue_color is not None
    assert result.confidence >= 0
