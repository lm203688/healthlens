"""数据连接路由 - 数据源管理、同步"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User
from app.models.data_connection import DataConnection
from app.api.deps import get_current_user
from cryptography.fernet import Fernet
import hashlib
import base64
from app.config import settings


def _get_cipher() -> Fernet:
    key = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token: str) -> str:
    return _get_cipher().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _get_cipher().decrypt(encrypted.encode()).decode()


ALLOWED_SOURCE_TYPES = {"huawei_health", "apple_health", "withings", "xiaomi_health", "hospital_lis", "open_wearables"}

# Open Wearables 支持的设备提供商列表（mock 模式下返回，真实模式下从 OW API 获取）
OW_PROVIDERS = [
    {"id": "garmin", "name": "Garmin", "type": "watch", "icon": "⌚"},
    {"id": "oura", "name": "Oura Ring", "type": "ring", "icon": "💍"},
    {"id": "whoop", "name": "WHOOP", "type": "band", "icon": "📿"},
    {"id": "polar", "name": "Polar", "type": "watch", "icon": "⌚"},
    {"id": "suunto", "name": "Suunto", "type": "watch", "icon": "⌚"},
    {"id": "strava", "name": "Strava", "type": "app", "icon": "🏃"},
    {"id": "fitbit", "name": "Fitbit", "type": "watch", "icon": "⌚"},
    {"id": "ultrahuman", "name": "Ultrahuman", "type": "ring", "icon": "💍"},
    {"id": "withings", "name": "Withings", "type": "scale", "icon": "⚖️"},
    {"id": "google_health", "name": "Google Health", "type": "platform", "icon": "📱"},
]

router = APIRouter(tags=["connections"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConnectionCreateInput(BaseModel):
    """添加数据源的请求参数"""
    source_type: str  # e.g. "apple_health", "google_fit", "manual", "hospital_portal"
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    config: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_connection(
    body: ConnectionCreateInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    添加数据源连接
    """
    if body.source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported source_type: '{body.source_type}'. Allowed: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
        )

    encrypted_access = encrypt_token(body.access_token) if body.access_token else None
    encrypted_refresh = encrypt_token(body.refresh_token) if body.refresh_token else None

    connection = DataConnection(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        source_type=body.source_type,
        access_token=encrypted_access,
        refresh_token=encrypted_refresh,
        token_expires_at=body.token_expires_at,
        config=body.config,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    return {
        "success": True,
        "data": {
            "id": str(connection.id),
            "source_type": connection.source_type,
            "is_active": connection.is_active,
            "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
            "created_at": connection.created_at.isoformat() if connection.created_at else None,
        },
    }


@router.get("/", response_model=dict)
async def list_connections(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前用户的所有数据源连接
    """
    query = (
        select(DataConnection)
        .where(DataConnection.user_id == current_user.id)
        .order_by(DataConnection.created_at.desc())
    )
    count_query = select(func.count()).select_from(DataConnection).where(
        DataConnection.user_id == current_user.id
    )

    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    connections = result.scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    data = []
    for conn in connections:
        data.append({
            "id": str(conn.id),
            "source_type": conn.source_type,
            "is_active": conn.is_active,
            "last_sync_at": conn.last_sync_at.isoformat() if conn.last_sync_at else None,
            "created_at": conn.created_at.isoformat() if conn.created_at else None,
            # 不返回 access_token / refresh_token
        })

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.delete("/{conn_id}", response_model=dict)
async def delete_connection(
    conn_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除数据源连接
    """
    result = await db.execute(
        select(DataConnection).where(
            DataConnection.id == conn_id,
            DataConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await db.delete(connection)
    await db.commit()

    return {
        "success": True,
        "data": None,
        "meta": {"message": f"Connection {conn_id} deleted"},
    }


@router.post("/{conn_id}/sync")
async def sync_connection(
    conn_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步数据连接 - 调用对应连接器拉取最新数据"""
    result = await db.execute(
        select(DataConnection).where(
            DataConnection.id == conn_id,
            DataConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.connectors.base import ConnectorRegistry

    connector = ConnectorRegistry.get(connection.source_type)
    if not connector:
        return {
            "success": False,
            "error": f"No connector registered for '{connection.source_type}'",
        }

    try:
        decrypted_token = decrypt_token(connection.access_token) if connection.access_token else None
        sync_result = await connector.sync_data(
            access_token=decrypted_token,
            user_id=str(current_user.id),
            since=connection.last_sync_at,
        )
        connection.last_sync_at = datetime.utcnow()
        connection.sync_status = "completed"
        await db.commit()

        return {
            "success": True,
            "data": {
                "connection_id": str(connection.id),
                "sync_status": "completed",
                "synced_items": sync_result.get("items_count", 0),
                "message": sync_result.get("message", "Sync completed"),
            },
        }
    except NotImplementedError:
        connection.sync_status = "pending"
        connection.last_sync_at = datetime.utcnow()
        await db.commit()
        return {
            "success": True,
            "data": {
                "connection_id": str(connection.id),
                "sync_status": "pending",
                "message": f"Connector '{connection.source_type}' not yet implemented. Coming in Phase 1.5.",
            },
        }
    except Exception as e:
        connection.sync_status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


# ---------------------------------------------------------------------------
# Open Wearables 专属端点
# ---------------------------------------------------------------------------

@router.get("/open-wearables/providers")
async def list_ow_providers(
    current_user: User = Depends(get_current_user),
):
    """获取 Open Wearables 支持的设备提供商列表"""
    # 尝试从 OW API 获取（如果可达），否则返回内置列表
    try:
        from app.connectors.open_wearables import OpenWearablesConnector
        connector = OpenWearablesConnector()
        health = await connector.health_check()
        if health.get("status") == "ok":
            # OW 可达，返回实时数据
            client = await connector._get_client()
            resp = await client.get("/api/v1/providers")
            resp.raise_for_status()
            providers = resp.json().get("providers", [])
            return {
                "success": True,
                "data": {
                    "providers": [{"id": p, "name": p.title(), "type": "generic", "icon": "⌚"} for p in providers],
                    "ow_status": "online",
                },
            }
    except Exception:
        pass
    # Fallback: 返回内置列表
    return {
        "success": True,
        "data": {
            "providers": OW_PROVIDERS,
            "ow_status": "mock",
        },
    }


@router.post("/open-wearables/connect")
async def connect_ow(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """连接 Open Wearables 设备（mock 模式下直接创建连接，真实模式下走 OAuth）"""
    provider = body.get("provider", "")
    if provider not in [p["id"] for p in OW_PROVIDERS]:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # Mock 模式：生成一个 OW 用户 ID 并创建连接
    ow_user_id = str(uuid.uuid4())
    encrypted_token = encrypt_token(ow_user_id)

    connection = DataConnection(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        source_type="open_wearables",
        access_token=encrypted_token,
        refresh_token=None,
        token_expires_at=None,
        config={"provider": provider, "ow_user_id": ow_user_id},
        sync_status="pending",
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    return {
        "success": True,
        "data": {
            "id": str(connection.id),
            "source_type": "open_wearables",
            "provider": provider,
            "ow_user_id": ow_user_id,
            "is_active": True,
            "message": f"Connected to {provider} via Open Wearables",
        },
    }


@router.post("/open-wearables/sync-all")
async def sync_all_ow_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步所有 Open Wearables 连接"""
    result = await db.execute(
        select(DataConnection).where(
            DataConnection.user_id == current_user.id,
            DataConnection.source_type == "open_wearables",
            DataConnection.is_active == True,
        )
    )
    connections = result.scalars().all()
    if not connections:
        return {"success": True, "data": {"synced": 0, "message": "No Open Wearables connections found"}}

    from app.connectors.base import ConnectorRegistry
    connector = ConnectorRegistry.get("open_wearables")
    if not connector:
        return {"success": False, "error": "Open Wearables connector not available"}

    results = []
    for conn in connections:
        try:
            decrypted_token = decrypt_token(conn.access_token) if conn.access_token else None
            sync_result = await connector.sync_data(
                access_token=decrypted_token,
                user_id=str(current_user.id),
                since=conn.last_sync_at,
            )
            conn.last_sync_at = datetime.utcnow()
            conn.sync_status = "completed"
            await db.commit()
            results.append({
                "connection_id": str(conn.id),
                "status": "completed",
                "items_count": sync_result.get("items_count", 0),
            })
        except Exception as e:
            conn.sync_status = "failed"
            await db.commit()
            results.append({
                "connection_id": str(conn.id),
                "status": "failed",
                "error": str(e),
            })

    return {"success": True, "data": {"results": results, "synced": len([r for r in results if r["status"] == "completed"])}}
