# -*- coding: utf-8 -*-
"""药物相关 Schema"""

from pydantic import BaseModel


class MedicationRecommendationOutput(BaseModel):
    """药物推荐输出"""

    id: str
    drug_name: str
    drug_code: str | None
    dosage: float | None
    dosage_unit: str | None
    frequency: str | None
    route: str | None
    pgx_evidence: str | None
