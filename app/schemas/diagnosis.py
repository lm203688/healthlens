# -*- coding: utf-8 -*-
"""诊断相关 Schema"""

from pydantic import BaseModel


class DiagnosisTriggerInput(BaseModel):
    """诊断触发输入"""

    user_id: str | None = None  # 不传则用当前用户


class DiagnosisResultOutput(BaseModel):
    """诊断结果输出"""

    id: str
    diagnosis_text: str
    icd_code: str | None
    confidence: float
    severity: str | None
    status: str
    is_ai_generated: bool
    reviewed_by: str | None
    created_at: str
