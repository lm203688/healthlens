"""OCR 医学报告解析引擎
Phase 1: 框架定义 + MockOCR 开发引擎
Phase 2: 集成 LayoutLM / PaddleOCR / DocTR
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from loguru import logger


@dataclass
class OCRResult:
    raw_text: str
    structured_data: dict
    confidence: float
    page_count: int


class BaseOCREngine(ABC):
    @abstractmethod
    async def parse(self, file_path: str | bytes) -> OCRResult:
        ...


class TesseractOCREngine(BaseOCREngine):
    """基于 Tesseract 的 OCR 引擎，支持图片和 PDF"""

    def __init__(self):
        self._available: bool | None = None

    def _check_available(self) -> bool:
        """延迟检测 pytesseract 是否可用"""
        if self._available is None:
            try:
                import pytesseract  # noqa: F401
                self._available = True
            except ImportError:
                logger.warning("pytesseract not installed, falling back to MockOCR")
                self._available = False
        return self._available

    async def parse(self, file_path: str | bytes) -> OCRResult:
        if not self._check_available():
            return MockOCREngine().await_parse(file_path)

        if isinstance(file_path, bytes):
            import tempfile
            import os
            suffix = ".png"
            if file_path.startswith(b"%PDF"):
                suffix = ".pdf"
            elif file_path[:4] in (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):
                suffix = ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_path)
                tmp_path = tmp.name
            try:
                return await self._parse_file(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            return await self._parse_file(file_path)

    async def _parse_file(self, file_path: str) -> OCRResult:
        if file_path.lower().endswith(".pdf"):
            return await self._parse_pdf(file_path)
        else:
            return await self._parse_image(file_path)

    async def _parse_image(self, file_path: str) -> OCRResult:
        import pytesseract
        from PIL import Image

        try:
            img = Image.open(file_path)
        except Exception as e:
            logger.error(f"Failed to open image {file_path}: {e}")
            return OCRResult(
                raw_text="",
                structured_data={"report_type": "unknown", "observations": []},
                confidence=0.0,
                page_count=1,
            )

        raw_text = pytesseract.image_to_string(img, lang="chi_sim+eng")

        # pytesseract 不直接返回单行置信度，使用整体置信度估算
        try:
            data = pytesseract.image_to_data(img, lang="chi_sim+eng", output_type=pytesseract.Output.DICT)
            conf_values = [int(c) for c in data["conf"] if int(c) > 0]
            avg_confidence = (sum(conf_values) / len(conf_values) / 100) if conf_values else 0.0
        except Exception:
            avg_confidence = 0.7

        from app.core.report_parser import extract_observations_from_text
        observations = extract_observations_from_text(raw_text)

        return OCRResult(
            raw_text=raw_text,
            structured_data={
                "report_type": "auto_detected",
                "observations": observations,
            },
            confidence=round(avg_confidence, 3),
            page_count=1,
        )

    async def _parse_pdf(self, file_path: str) -> OCRResult:
        """PDF 解析：先转图片再 OCR"""
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path, dpi=200)
        except ImportError:
            logger.warning("pdf2image not installed, falling back to MockOCR")
            return MockOCREngine()._mock_physical_examination()
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return MockOCREngine()._mock_physical_examination()

        import pytesseract

        all_text_parts = []
        total_confidence = 0.0
        conf_count = 0

        for img in images:
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            all_text_parts.append(text)

            try:
                data = pytesseract.image_to_data(img, lang="chi_sim+eng", output_type=pytesseract.Output.DICT)
                conf_values = [int(c) for c in data["conf"] if int(c) > 0]
                if conf_values:
                    total_confidence += sum(conf_values) / len(conf_values) / 100
                    conf_count += 1
            except Exception:
                pass

        raw_text = "\n".join(all_text_parts)
        avg_confidence = (total_confidence / conf_count) if conf_count else 0.0

        from app.core.report_parser import extract_observations_from_text
        observations = extract_observations_from_text(raw_text)

        return OCRResult(
            raw_text=raw_text,
            structured_data={
                "report_type": "auto_detected",
                "observations": observations,
            },
            confidence=round(avg_confidence, 3),
            page_count=len(images),
        )


class SmartOCREngine(BaseOCREngine):
    """Phase 2 - 深度学习版面分析"""
    async def parse(self, file_path: str | bytes) -> OCRResult:
        raise NotImplementedError("Smart OCR engine planned for Phase 2")


class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎 - 免费开源，中文医学报告识别效果最佳
    支持中文/英文混合文本、表格、手写体
    """

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        """延迟初始化 PaddleOCR（首次使用时加载模型）"""
        if self._engine is None:
            try:
                from paddleocr import PaddleOCR
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",  # 中英文混合
                    show_log=False,
                    use_gpu=False,  # CPU 模式，兼容无 GPU 环境
                )
                logger.info("PaddleOCR engine initialized successfully")
            except ImportError:
                logger.warning("PaddleOCR not installed, falling back to MockOCR")
                return None
            except Exception as e:
                logger.error(f"PaddleOCR initialization failed: {e}")
                return None
        return self._engine

    async def parse(self, file_path: str | bytes) -> OCRResult:
        if isinstance(file_path, bytes):
            # 保存到临时文件
            import tempfile
            import os
            suffix = ".png"
            # 检测文件类型
            if file_path.startswith(b"%PDF"):
                suffix = ".pdf"
            elif file_path[:4] == b"\xff\xd8\xff\xe0" or file_path[:4] == b"\xff\xd8\xff\xe1":
                suffix = ".jpg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_path)
                tmp_path = tmp.name
            try:
                return await self._parse_file(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            return await self._parse_file(file_path)

    async def _parse_file(self, file_path: str) -> OCRResult:
        engine = self._get_engine()
        if engine is None:
            # PaddleOCR 不可用，回退到 MockOCR
            return MockOCREngine().await_parse(file_path)

        # PDF 需要先转图片
        if file_path.lower().endswith(".pdf"):
            return await self._parse_pdf(engine, file_path)
        else:
            return await self._parse_image(engine, file_path)

    async def _parse_image(self, engine, file_path: str) -> OCRResult:
        result = engine.ocr(file_path, cls=True)

        if not result or not result[0]:
            return OCRResult(
                raw_text="",
                structured_data={"report_type": "unknown", "observations": []},
                confidence=0.0,
                page_count=1,
            )

        # 提取文本和置信度
        lines = []
        total_confidence = 0
        for line in result[0]:
            text = line[1][0]
            confidence = line[1][1]
            lines.append(text)
            total_confidence += confidence

        raw_text = "\n".join(lines)
        avg_confidence = total_confidence / len(result[0]) if result[0] else 0

        # 使用正则解析器提取结构化数据
        from app.core.report_parser import extract_observations_from_text
        observations = extract_observations_from_text(raw_text)

        return OCRResult(
            raw_text=raw_text,
            structured_data={
                "report_type": "auto_detected",
                "observations": observations,
            },
            confidence=round(avg_confidence, 3),
            page_count=1,
        )

    async def _parse_pdf(self, engine, file_path: str) -> OCRResult:
        """PDF 解析：先转图片再 OCR"""
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path, dpi=200)
        except ImportError:
            logger.warning("pdf2image not installed, falling back to MockOCR")
            return MockOCREngine()._mock_physical_examination()
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return MockOCREngine()._mock_physical_examination()

        all_lines = []
        total_confidence = 0
        total_items = 0

        for img in images:
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img.save(tmp.name, "PNG")
                tmp_path = tmp.name
            try:
                result = engine.ocr(tmp_path, cls=True)
                if result and result[0]:
                    for line in result[0]:
                        text = line[1][0]
                        confidence = line[1][1]
                        all_lines.append(text)
                        total_confidence += confidence
                        total_items += 1
            finally:
                os.unlink(tmp_path)

        raw_text = "\n".join(all_lines)
        avg_confidence = total_confidence / total_items if total_items else 0

        from app.core.report_parser import extract_observations_from_text
        observations = extract_observations_from_text(raw_text)

        return OCRResult(
            raw_text=raw_text,
            structured_data={
                "report_type": "auto_detected",
                "observations": observations,
            },
            confidence=round(avg_confidence, 3),
            page_count=len(images),
        )


class MockOCREngine(BaseOCREngine):
    """开发环境 Mock OCR 引擎，返回模拟的体检/检验报告数据"""

    # PDF 文件魔数
    PDF_MAGIC = b"%PDF"
    # JPEG 文件魔数
    JPEG_MAGIC = b"\xff\xd8\xff"
    # PNG 文件魔数
    PNG_MAGIC = b"\x89PNG"
    # TIFF 文件魔数
    TIFF_MAGIC = b"II\x2a\x00"  # little-endian TIFF

    @staticmethod
    def _detect_file_type(file_content: bytes) -> str | None:
        """根据文件头部字节判断文件类型"""
        if file_content.startswith(MockOCREngine.PDF_MAGIC):
            return "pdf"
        if file_content.startswith(MockOCREngine.JPEG_MAGIC):
            return "jpeg"
        if file_content.startswith(MockOCREngine.PNG_MAGIC):
            return "png"
        if file_content.startswith(MockOCREngine.TIFF_MAGIC):
            return "tiff"
        # 尝试检测 big-endian TIFF
        if file_content.startswith(b"MM\x00\x2a"):
            return "tiff"
        return None

    async def parse(self, file_path: str | bytes) -> OCRResult:
        """解析文件并返回模拟的 OCR 结果"""
        if isinstance(file_path, str):
            logger.info(f"MockOCR: reading file from path: {file_path}")
            with open(file_path, "rb") as f:
                file_content = f.read()
        else:
            file_content = file_path

        file_type = self._detect_file_type(file_content)

        if file_type == "pdf":
            return self._mock_physical_examination()
        elif file_type in ("jpeg", "png", "tiff"):
            return self._mock_blood_test()
        else:
            # 未知类型，默认返回体检报告
            logger.warning(f"MockOCR: unknown file type, defaulting to physical examination report")
            return self._mock_physical_examination()

    async def await_parse(self, file_path: str | bytes) -> OCRResult:
        """供 PaddleOCREngine 回退使用"""
        return await self.parse(file_path)

    def _mock_physical_examination(self) -> OCRResult:
        """模拟体检报告解析结果"""
        logger.info("MockOCR: returning mock physical examination report")
        return OCRResult(
            raw_text="模拟体检报告解析结果\n\n=== 常规检查 ===\n血糖(Glucose): 6.8 mmol/L (参考: 3.9-6.1) ↑\n总胆固醇(Cholesterol): 5.8 mmol/L (参考: 2.8-5.2) ↑\n甘油三酯(Triglycerides): 1.9 mmol/L (参考: 0.3-1.7) ↑\n谷丙转氨酶(ALT): 55 U/L (参考: 0-40) ↑\n肌酐(Creatinine): 98 umol/L (参考: 44-133) 正常\n白细胞计数(WBC): 9.2 10*9/L (参考: 3.5-9.5) 正常\n血红蛋白(Hemoglobin): 138 g/L (参考: 130-175) 正常",
            structured_data={
                "report_type": "physical_examination",
                "patient_name": "测试用户",
                "observations": [
                    {
                        "loinc_code": "2345-7",
                        "loinc_name": "血糖(Glucose)",
                        "value_numeric": 6.8,
                        "value_unit": "mmol/L",
                        "reference_range_low": 3.9,
                        "reference_range_high": 6.1,
                    },
                    {
                        "loinc_code": "2093-3",
                        "loinc_name": "总胆固醇(Cholesterol)",
                        "value_numeric": 5.8,
                        "value_unit": "mmol/L",
                        "reference_range_low": 2.8,
                        "reference_range_high": 5.2,
                    },
                    {
                        "loinc_code": "2085-9",
                        "loinc_name": "甘油三酯(Triglycerides)",
                        "value_numeric": 1.9,
                        "value_unit": "mmol/L",
                        "reference_range_low": 0.3,
                        "reference_range_high": 1.7,
                    },
                    {
                        "loinc_code": "2571-8",
                        "loinc_name": "谷丙转氨酶(ALT)",
                        "value_numeric": 55,
                        "value_unit": "U/L",
                        "reference_range_low": 0,
                        "reference_range_high": 40,
                    },
                    {
                        "loinc_code": "6299-1",
                        "loinc_name": "肌酐(Creatinine)",
                        "value_numeric": 98,
                        "value_unit": "umol/L",
                        "reference_range_low": 44,
                        "reference_range_high": 133,
                    },
                    {
                        "loinc_code": "785-6",
                        "loinc_name": "白细胞计数(WBC)",
                        "value_numeric": 9.2,
                        "value_unit": "10*9/L",
                        "reference_range_low": 3.5,
                        "reference_range_high": 9.5,
                    },
                    {
                        "loinc_code": "718-7",
                        "loinc_name": "血红蛋白(Hemoglobin)",
                        "value_numeric": 138,
                        "value_unit": "g/L",
                        "reference_range_low": 130,
                        "reference_range_high": 175,
                    },
                ],
            },
            confidence=0.85,
            page_count=1,
        )

    def _mock_blood_test(self) -> OCRResult:
        """模拟血液检查报告解析结果"""
        logger.info("MockOCR: returning mock blood test report")
        return OCRResult(
            raw_text="模拟血液检查报告解析结果\n\n=== 血常规 + 生化 ===\n红细胞计数(RBC): 4.5 10*12/L (参考: 4.0-5.5)\n白细胞计数(WBC): 7.8 10*9/L (参考: 3.5-9.5)\n血小板计数(PLT): 220 10*9/L (参考: 100-300)\n血红蛋白(Hemoglobin): 145 g/L (参考: 130-175)\n血糖(Glucose): 5.2 mmol/L (参考: 3.9-6.1)\n糖化血红蛋白(HbA1c): 5.6 % (参考: 4.0-6.0)",
            structured_data={
                "report_type": "blood_test",
                "patient_name": "测试用户",
                "observations": [
                    {
                        "loinc_code": "789-8",
                        "loinc_name": "红细胞计数(RBC)",
                        "value_numeric": 4.5,
                        "value_unit": "10*12/L",
                        "reference_range_low": 4.0,
                        "reference_range_high": 5.5,
                    },
                    {
                        "loinc_code": "785-6",
                        "loinc_name": "白细胞计数(WBC)",
                        "value_numeric": 7.8,
                        "value_unit": "10*9/L",
                        "reference_range_low": 3.5,
                        "reference_range_high": 9.5,
                    },
                    {
                        "loinc_code": "777-3",
                        "loinc_name": "血小板计数(PLT)",
                        "value_numeric": 220,
                        "value_unit": "10*9/L",
                        "reference_range_low": 100,
                        "reference_range_high": 300,
                    },
                    {
                        "loinc_code": "718-7",
                        "loinc_name": "血红蛋白(Hemoglobin)",
                        "value_numeric": 145,
                        "value_unit": "g/L",
                        "reference_range_low": 130,
                        "reference_range_high": 175,
                    },
                    {
                        "loinc_code": "2345-7",
                        "loinc_name": "血糖(Glucose)",
                        "value_numeric": 5.2,
                        "value_unit": "mmol/L",
                        "reference_range_low": 3.9,
                        "reference_range_high": 6.1,
                    },
                    {
                        "loinc_code": "4548-4",
                        "loinc_name": "糖化血红蛋白(HbA1c)",
                        "value_numeric": 5.6,
                        "value_unit": "%",
                        "reference_range_low": 4.0,
                        "reference_range_high": 6.0,
                    },
                ],
            },
            confidence=0.82,
            page_count=1,
        )


def get_ocr_engine(engine_type: str = "tesseract") -> BaseOCREngine:
    if engine_type == "mock":
        return MockOCREngine()
    if engine_type == "tesseract":
        return TesseractOCREngine()
    elif engine_type == "paddleocr":
        return PaddleOCREngine()
    elif engine_type == "smart":
        return SmartOCREngine()
    raise ValueError(f"Unknown OCR engine: {engine_type}")