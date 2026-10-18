"""国标闸门 API

路由前缀: /api/v1/national-standard

提供 GB/T 20001.10-2014 条款映射的公开查询与文档检查接口。
所有响应都带 disclaimer，明确 wellness 边界。

认证策略：
- GET 列表/详情/条款 → 公开
- POST 检查文档 / GET 合规报告 → 需登录
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.lib.national_standard_gate import (
    build_compliance_report,
    get_standard_detail,
    list_available_standards,
    list_clauses,
    run_national_standard_gate,
)
from app.core.compliance.gb2001 import NationalStandardError

router = APIRouter()


class CheckRequest(BaseModel):
    """文档检查请求体"""
    doc_text: str = Field(..., min_length=1, description="待检查的文档文本")
    standard_id: str = Field(
        default="GB/T 20001.10-2014",
        description="国标编号",
    )


@router.get("/standards", summary="列出可用国标")
async def list_standards():
    """列出可用的国标（公开）。"""
    return {
        "success": True,
        "not_clinical": True,
        "data": list_available_standards(),
        "disclaimer": (
            "本国标闸门为健康管理服务文档提供结构化参考，"
            "非医疗诊断标准，不构成法律或监管合规声明。"
        ),
    }


@router.get("/standards/{standard_id:path}", summary="国标详情")
async def get_standard(standard_id: str):
    """国标详情（公开）。"""
    try:
        detail = get_standard_detail(standard_id)
    except NationalStandardError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "success": True,
        "not_clinical": True,
        "data": detail,
    }


@router.post("/check", summary="检查文档合规性")
async def check_document(
    body: CheckRequest,
    current_user: User = Depends(get_current_user),
):
    """对文档运行国标闸门（需登录）。"""
    result = await run_national_standard_gate(
        doc_text=body.doc_text,
        standard_id=body.standard_id,
    )
    return result


@router.get("/clauses/{standard_id:path}", summary="条款列表")
async def list_std_clauses(standard_id: str):
    """指定国标的条款列表（公开）。"""
    try:
        clauses = list_clauses(standard_id)
    except NationalStandardError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "success": True,
        "not_clinical": True,
        "standard_id": standard_id,
        "data": clauses,
    }


@router.get("/compliance-report", summary="合规报告摘要")
async def compliance_report(
    current_user: User = Depends(get_current_user),
):
    """国标闸门合规报告摘要（需登录）。"""
    report = build_compliance_report()
    return {
        "success": True,
        "not_clinical": True,
        "data": report,
    }


__all__ = ["router"]
