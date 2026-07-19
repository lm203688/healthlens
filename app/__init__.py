from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} starting...")

    # 安全检查
    security_warnings = settings.check_security()
    for w in security_warnings:
        logger.warning(f"[SECURITY] {w}")

    # 非调试模式下，不安全密钥直接阻止启动
    if not settings.DEBUG and security_warnings:
        critical_issues = [w for w in security_warnings if "JWT_SECRET_KEY" in w or "MINIO_SECRET_KEY" in w]
        if critical_issues:
            logger.critical("生产环境检测到不安全密钥配置，拒绝启动。请在 .env 中设置安全的密钥值。")
            raise SystemExit(1)

    yield
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics middleware
    from app.utils.metrics import RequestMetricsMiddleware
    app.add_middleware(RequestMetricsMiddleware)

    # 注册路由
    from app.api.auth import router as auth_router
    from app.api.records import router as records_router
    from app.api.observations import router as observations_router
    from app.api.diagnosis import router as diagnosis_router
    from app.api.medications import router as medications_router
    from app.api.tcm import router as tcm_router
    from app.api.connections import router as connections_router
    from app.api.genome import router as genome_router
    from app.api.reports import router as reports_router
    from app.api.profiles import router as profiles_router
    from app.api.dashboard import router as dashboard_router
    from app.api.goals import router as goals_router
    from app.api.notifications import router as notifications_router
    from app.api.medication_adherence import router as adherence_router

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
    app.include_router(records_router, prefix="/api/v1/records", tags=["数据接入"])
    app.include_router(observations_router, prefix="/api/v1/observations", tags=["健康数据"])
    app.include_router(diagnosis_router, prefix="/api/v1/diagnosis", tags=["西医诊断"])
    app.include_router(medications_router, prefix="/api/v1/medications", tags=["西药"])
    app.include_router(tcm_router, prefix="/api/v1/tcm", tags=["中医"])
    app.include_router(connections_router, prefix="/api/v1/connections", tags=["数据连接"])
    app.include_router(genome_router, prefix="/api/v1/genome", tags=["基因组"])
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["报告"])
    app.include_router(profiles_router, prefix="/api/v1/profiles", tags=["健康档案"])
    app.include_router(dashboard_router, prefix="/api/v1/dashboard", tags=["仪表盘"])
    app.include_router(goals_router, prefix="/api/v1/goals", tags=["健康目标"])
    app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["通知中心"])
    app.include_router(adherence_router, prefix="/api/v1/adherence", tags=["用药依从性"])

    # 健康检查端点（Docker HEALTHCHECK 使用）
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/metrics")
    async def metrics():
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from starlette.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app

app = create_app()
