"""报告管理路由 - 上传、查询、删除、重新解析健康报告"""
import os
import uuid
import json
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.record import HealthRecord
from app.api.deps import get_current_user
from loguru import logger

router = APIRouter(tags=["records"])

UPLOAD_DIR = Path("data/uploads")


def ensure_upload_dir():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_record(
    file: UploadFile = File(..., description="健康报告文件（PDF/图片）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传健康报告文件，保存到本地存储"""
    allowed_types = {"application/pdf", "image/jpeg", "image/png", "image/tiff"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, JPEG, PNG, TIFF",
        )

    ensure_upload_dir()
    record_id = str(uuid.uuid4())
    user_dir = UPLOAD_DIR / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = file.filename or "unknown"
    file_path = user_dir / f"{record_id}_{safe_filename}"

    # 读取文件内容并保存
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 触发 OCR 解析
    from app.services.ocr_service import process_report

    parse_result = await process_report(
        file_content=content,
        filename=safe_filename,
        user_id=str(current_user.id),
        db=db,
        record_id=record_id,
    )

    record = HealthRecord(
        id=record_id,
        user_id=current_user.id,
        filename=safe_filename,
        file_path=str(file_path),
        file_size=len(content),
        content_type=file.content_type or "application/octet-stream",
        status=parse_result["status"],
        observations_count=parse_result["extracted_items"],
        parse_result=json.dumps({
            "message": parse_result["message"],
            "observations_preview": parse_result.get("observations", []),
        }),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    logger.info(f"Record uploaded: {record_id} by user {current_user.id}, size={len(content)}, status={record.status}")

    return {
        "success": True,
        "data": {
            "id": str(record.id),
            "filename": record.filename,
            "file_size": record.file_size,
            "content_type": record.content_type,
            "status": record.status,
            "observations_count": record.observations_count,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        },
    }


@router.get("/")
async def list_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的健康报告列表（分页）"""
    query = select(HealthRecord).where(HealthRecord.user_id == current_user.id)
    count_query = select(func.count()).select_from(HealthRecord).where(HealthRecord.user_id == current_user.id)

    if status_filter:
        query = query.where(HealthRecord.status == status_filter)
        count_query = count_query.where(HealthRecord.status == status_filter)

    query = query.order_by(HealthRecord.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    records = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for r in records:
        data.append({
            "id": str(r.id),
            "filename": r.filename,
            "file_size": r.file_size,
            "content_type": r.content_type,
            "status": r.status,
            "observations_count": r.observations_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "success": True,
        "data": data,
        "meta": {"page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size},
    }


@router.get("/{record_id}")
async def get_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定报告的详细信息"""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id,
            HealthRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    parse_result = None
    if record.parse_result:
        try:
            parse_result = json.loads(record.parse_result)
        except json.JSONDecodeError:
            parse_result = None

    return {
        "success": True,
        "data": {
            "id": str(record.id),
            "filename": record.filename,
            "file_size": record.file_size,
            "content_type": record.content_type,
            "status": record.status,
            "observations_count": record.observations_count,
            "parse_result": parse_result,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        },
    }


@router.delete("/{record_id}")
async def delete_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除指定报告"""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id,
            HealthRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # 删除本地文件
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)
        logger.info(f"Deleted file: {record.file_path}")

    await db.delete(record)
    await db.commit()

    return {"success": True, "data": None, "meta": {"message": "Record deleted"}}


@router.post("/{record_id}/reprocess")
async def reprocess_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重新解析报告"""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id,
            HealthRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    record.status = "uploaded"
    record.error_message = None
    await db.commit()

    return {
        "success": True,
        "data": {
            "id": str(record.id),
            "status": "reprocessing",
            "message": "Record marked for reprocessing",
        },
    }
