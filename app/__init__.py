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

    # 初始化日志配置
    from app.utils.logging_config import setup_logging
    setup_logging()

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

    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from app.api.auth import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

    # 请求 ID 追踪中间件
    from app.utils.request_id import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)

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
    from app.api.knowledge import router as knowledge_router

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
    app.include_router(knowledge_router, prefix="/api/v1/knowledge", tags=["中医古籍知识"])

    # 健康检查端点（Docker HEALTHCHECK 使用）
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/metrics")
    async def metrics():
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from starlette.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        from loguru import logger
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(f"Unhandled exception | request_id={request_id} | path={request.url.path} | error={exc}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "request_id": request_id,
                "detail": str(exc) if settings.DEBUG else None,
            },
        )

    return app

app = create_app()
