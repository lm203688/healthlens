# -*- coding: utf-8 -*-
"""观察指标相关 Schema"""

from pydantic import BaseModel


class ObservationOutput(BaseModel):
    """观察指标输出"""

    id: str
    loinc_code: str
    loinc_name: str | None
    value_numeric: float | None
    value_string: str | None
    value_unit: str | None
    reference_range_low: float | None
    reference_range_high: float | None
    source: str
    recorded_at: str
    is_abnormal: bool | None = None  # 计算字段


class ObservationSummary(BaseModel):
    """观察指标汇总"""

    total_items: int
    abnormal_count: int
    categories: list[dict]  # [{"name": "血糖", "code": "2345-7", "latest": 95.0, "unit": "mg/dL", "is_abnormal": false}]
