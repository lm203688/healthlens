"""OCR 服务 - 协调 OCR 引擎与数据存储"""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from app.core.ocr_engine import get_ocr_engine, OCRResult, OCRUnavailableError
from app.models.observation import HealthObservation
from app.config import settings


async def process_report(file_content: bytes, filename: str, user_id: str, db: AsyncSession, record_id: str) -> dict:
    """处理上传的报告文件：OCR解析 -> 结构化数据 -> 存储"""
    engine_type = settings.OCR_ENGINE
    engine = get_ocr_engine(engine_type)

    # OCR 解析
    try:
        ocr_result: OCRResult = await engine.parse(file_content)
    except OCRUnavailableError as e:
        # 失败上报：绝不返回伪造的检验数值（P0-6 医疗级事故隐患修复）
        logger.warning(f"OCR engine unavailable: {e}")
        return {
            "status": "unavailable",
            "message": f"OCR 服务不可用：{e}。请配置真实 OCR 后端（pytesseract/PaddleOCR）后重试。",
            "extracted_items": 0,
        }
    except NotImplementedError as e:
        logger.warning(f"OCR engine not implemented: {e}")
        return {
            "status": "pending",
            "message": f"OCR engine ({engine_type}) not yet configured. Set OCR_ENGINE=mock in .env for development.",
            "extracted_items": 0,
        }
    except Exception as e:
        logger.error(f"OCR parsing failed: {e}")
        return {
            "status": "failed",
            "message": f"OCR parsing failed: {str(e)}",
            "extracted_items": 0,
        }

    # 提取观测指标并写入数据库
    observations_data = ocr_result.structured_data.get("observations", [])

    # 指标别名词典归一化（M02 P1 · #126）：附加 canonical_* 字段与 in_range/level。
    # 词典不可用时降级为原样返回，绝不阻塞 OCR 主流程。
    from app.core.report_parser import enrich_observations_with_dictionary

    try:
        observations_data = enrich_observations_with_dictionary(observations_data, stratum="adult_male")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"indicator_dict enrichment skipped: {e}")
        for _obs in observations_data:
            _obs.setdefault("normalized", False)
            _obs.setdefault("normalize_reason", f"enrichment_error: {e}")

    created_count = 0

    for obs_item in observations_data:
        try:
            observation = HealthObservation(
                id=str(uuid.uuid4()),
                user_id=user_id,
                loinc_code=obs_item.get("loinc_code"),
                loinc_name=obs_item.get("loinc_name"),
                value_numeric=Decimal(str(obs_item["value_numeric"])) if obs_item.get("value_numeric") is not None else None,
                value_string=obs_item.get("value_string"),
                value_unit=obs_item.get("value_unit"),
                reference_range_low=Decimal(str(obs_item["reference_range_low"])) if obs_item.get("reference_range_low") is not None else None,
                reference_range_high=Decimal(str(obs_item["reference_range_high"])) if obs_item.get("reference_range_high") is not None else None,
                source="ocr",
                recorded_at=datetime.utcnow(),
            )
            db.add(observation)
            created_count += 1
        except Exception as e:
            logger.error(f"Failed to create observation: {e}")
            continue

    if created_count > 0:
        await db.commit()
        logger.info(f"Created {created_count} observations from OCR parse of record {record_id}")

    return {
        "status": "completed",
        "message": f"Parsed {ocr_result.page_count} page(s), extracted {created_count} observations",
        "extracted_items": created_count,
        "observations": observations_data[:5],  # 返回前5条作为预览
    }
