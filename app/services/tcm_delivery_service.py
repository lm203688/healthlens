"""中药配送服务 - 对接中药配方颗粒企业 API
Phase 1: 模拟药房接口
Phase 2: 对接一方制药/天江药业真实 API
"""
from loguru import logger
from datetime import datetime, timezone
import uuid


async def submit_to_pharmacy(formula_composition: dict, delivery_address: str, patient_name: str = "") -> dict:
    """向药房提交配方颗粒订单

    Phase 1: 返回模拟的订单确认
    Phase 2: 对接一方制药/天江药业/康美药业 API
    """
    order_id = str(uuid.uuid4())

    logger.info(f"Submitting order {order_id} to pharmacy: {len(formula_composition.get('composition', []))} herbs")

    return {
        "status": "accepted",
        "order_id": order_id,
        "pharmacy": "一方制药(模拟)",
        "estimated_delivery_days": 3,
        "fee_estimate": 68.00,  # 模拟费用
        "message": "Order submitted to pharmacy",
    }


async def query_order_status(order_id: str) -> dict:
    """查询订单状态"""
    # Phase 1: 模拟状态
    return {
        "order_id": order_id,
        "status": "processing",
        "pharmacy": "一方制药(模拟)",
        "tracking_number": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
