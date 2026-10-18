# -*- coding: utf-8 -*-
"""中药配送相关 Schema"""

from pydantic import BaseModel


class TcmOrderCreateInput(BaseModel):
    """中药订单创建输入"""

    formula_id: str
    delivery_address: str


class TcmOrderOutput(BaseModel):
    """中药订单输出"""

    id: str
    formula_id: str
    pharmacy_name: str | None
    order_status: str
    tracking_number: str | None
    total_fee: float | None
    ordered_at: str | None
    delivered_at: str | None
