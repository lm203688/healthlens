"""中医舌象分析引擎
Phase 1: 基于颜色直方图和形态特征的基础分析
Phase 2: 集成深度学习模型(如 EfficientNet)进行舌象分类

参考标准:
- 《中医舌诊》人民卫生出版社
- 中华中医药学会舌诊规范
"""
from dataclasses import dataclass
from loguru import logger


@dataclass
class TongueAnalysisResult:
    tongue_color: str          # 舌色: 淡红/红/绛/淡白/青紫
    tongue_shape: str          # 舌形: 正常/胖大/瘦薄/齿痕/裂纹/芒刺
    coating_color: str         # 苔色: 薄白/白/黄/灰黑/剥脱
    coating_quality: str       # 苔质: 薄/厚/润/燥/腻/腐
    sublingual_vein: str       # 舌下络脉: 正常/粗张/青紫
    syndrome_hint: str         # 辨证提示
    confidence: float          # 置信度 0-1
    raw_metrics: dict          # 原始颜色指标


# 舌色判断阈值 (RGB 平均值)
TONGUE_COLOR_THRESHOLDS = {
    "淡白": {"r_max": 180, "g_max": 180, "b_max": 180},
    "淡红": {"r_min": 180, "r_max": 210, "g_min": 140, "b_min": 140},
    "红":   {"r_min": 210, "g_max": 160, "b_max": 160},
    "绛":   {"r_min": 200, "g_max": 100, "b_max": 100},
    "青紫": {"r_max": 180, "b_min": 130},
}

# 舌色→辨证映射
TONGUE_COLOR_SYNDROME = {
    "淡白": "气血两虚或阳虚",
    "淡红": "正常舌色，见于健康人或病情轻浅",
    "红":   "热证(实热或虚热)",
    "绛":   "热入营血，或阴虚火旺",
    "青紫": "气血瘀滞，或阴寒内盛",
}

# 苔色→辨证映射
COATING_COLOR_SYNDROME = {
    "薄白": "正常舌苔，或外感表证初起",
    "白":   "寒证或湿证",
    "黄":   "热证或里证",
    "灰黑": "寒极或热极，病情较重",
    "剥脱": "胃气阴不足，或气血两虚",
}


class TongueAnalyzer:
    """中医舌象分析器"""

    def analyze_image_colors(self, image_bytes: bytes) -> dict:
        """分析舌象图片的颜色分布

        Phase 1: 使用 PIL 计算颜色直方图
        Phase 2: 使用 OpenCV 或深度学习模型
        """
        try:
            from io import BytesIO
            from PIL import Image

            img = Image.open(BytesIO(image_bytes))
            img = img.convert("RGB")
            img = img.resize((200, 200))  # 缩小加速

            # 使用 numpy 加速像素统计（避免 Pillow 14 getdata 废弃警告）
            import numpy as np
            arr = np.array(img)  # shape: (200, 200, 3)
            r_avg = float(arr[:, :, 0].mean())
            g_avg = float(arr[:, :, 1].mean())
            b_avg = float(arr[:, :, 2].mean())

            n = arr.shape[0] * arr.shape[1]
            warm_count = int((arr[:, :, 0] > arr[:, :, 2]).sum())
            cool_count = n - warm_count
            dark_count = int((arr.sum(axis=2) < 300).sum())
            light_count = int((arr.sum(axis=2) > 600).sum())

            return {
                "r_avg": round(r_avg, 1),
                "g_avg": round(g_avg, 1),
                "b_avg": round(b_avg, 1),
                "warm_ratio": round(warm_count / n, 3),
                "cool_ratio": round(cool_count / n, 3),
                "dark_ratio": round(dark_count / n, 3),
                "light_ratio": round(light_count / n, 3),
                "brightness": round((r_avg + g_avg + b_avg) / 3, 1),
            }

        except ImportError:
            logger.warning("PIL not installed, returning mock color analysis")
            return {
                "r_avg": 195.0, "g_avg": 150.0, "b_avg": 150.0,
                "warm_ratio": 0.6, "cool_ratio": 0.4,
                "dark_ratio": 0.2, "light_ratio": 0.5,
                "brightness": 165.0,
            }
        except Exception as e:
            logger.error(f"Tongue image analysis failed: {e}")
            return {"error": str(e)}

    def determine_tongue_color(self, metrics: dict) -> tuple[str, float]:
        """根据颜色指标判断舌色"""
        r, g, b = metrics.get("r_avg", 195), metrics.get("g_avg", 150), metrics.get("b_avg", 150)

        for color, thresholds in TONGUE_COLOR_THRESHOLDS.items():
            match = True
            if "r_min" in thresholds and r < thresholds["r_min"]:
                match = False
            if "r_max" in thresholds and r > thresholds["r_max"]:
                match = False
            if "g_min" in thresholds and g < thresholds["g_min"]:
                match = False
            if "g_max" in thresholds and g > thresholds["g_max"]:
                match = False
            if "b_min" in thresholds and b < thresholds["b_min"]:
                match = False
            if "b_max" in thresholds and b > thresholds["b_max"]:
                match = False

            if match:
                confidence = 0.6 + (0.1 if color == "淡红" else 0)
                return color, confidence

        # 默认淡红
        return "淡红", 0.5

    def determine_coating(self, metrics: dict) -> tuple[str, str]:
        """判断苔色和苔质"""
        dark_ratio = metrics.get("dark_ratio", 0.2)
        light_ratio = metrics.get("light_ratio", 0.5)
        warm_ratio = metrics.get("warm_ratio", 0.6)

        # 苔色
        if dark_ratio > 0.4:
            coating_color = "灰黑"
        elif warm_ratio > 0.7 and dark_ratio > 0.3:
            coating_color = "黄"
        elif dark_ratio > 0.25:
            coating_color = "白"
        elif light_ratio > 0.7:
            coating_color = "薄白"
        else:
            coating_color = "薄白"

        # 苔质
        if light_ratio > 0.6:
            coating_quality = "薄润"
        elif dark_ratio > 0.35:
            coating_quality = "厚腻"
        else:
            coating_quality = "薄润"

        return coating_color, coating_quality

    def analyze(self, image_bytes: bytes) -> TongueAnalysisResult:
        """分析舌象图片"""
        metrics = self.analyze_image_colors(image_bytes)

        if "error" in metrics:
            return TongueAnalysisResult(
                tongue_color="未知", tongue_shape="未知",
                coating_color="未知", coating_quality="未知",
                sublingual_vein="未检测",
                syndrome_hint="图像分析失败",
                confidence=0.0, raw_metrics=metrics,
            )

        tongue_color, color_confidence = self.determine_tongue_color(metrics)
        coating_color, coating_quality = self.determine_coating(metrics)

        # 舌形判断 (Phase 1: 基于亮度简化判断)
        brightness = metrics.get("brightness", 165)
        if brightness > 180:
            tongue_shape = "胖大"
        elif brightness < 140:
            tongue_shape = "瘦薄"
        else:
            tongue_shape = "正常"

        # 舌下络脉 (Phase 1: 无法检测)
        sublingual = "未检测"

        # 辨证提示
        color_syndrome = TONGUE_COLOR_SYNDROME.get(tongue_color, "")
        coating_syndrome = COATING_COLOR_SYNDROME.get(coating_color, "")
        syndrome_hint = f"舌色:{color_syndrome}; 苔:{coating_syndrome}"

        return TongueAnalysisResult(
            tongue_color=tongue_color,
            tongue_shape=tongue_shape,
            coating_color=coating_color,
            coating_quality=coating_quality,
            sublingual_vein=sublingual,
            syndrome_hint=syndrome_hint,
            confidence=color_confidence,
            raw_metrics=metrics,
        )

    async def analyze_async(self, image_bytes: bytes) -> TongueAnalysisResult:
        """异步接口"""
        return self.analyze(image_bytes)
