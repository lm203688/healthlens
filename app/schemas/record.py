# -*- coding: utf-8 -*-
"""健康记录相关 Schema"""

from pydantic import BaseModel


class RecordUploadResponse(BaseModel):
    """记录上传响应"""

    id: str
    filename: str
    status: str
    message: str


class RecordListItem(BaseModel):
    """记录列表项"""

    id: str
    filename: str
    source: str
    status: str
    created_at: str


class RecordDetail(BaseModel):
    """记录详情"""

    id: str
    filename: str
    source: str
    status: str
    observations_count: int
    created_at: str
    observations: list | None = None
