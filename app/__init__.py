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

    # 健康信号拦截中间件（wellness 平台的安全护栏）
    from app.middleware.emergency_interceptor import emergency_interceptor_middleware
    app.middleware("http")(emergency_interceptor_middleware)

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
    from app.api.axes import router as axes_router
    from app.api.repair import router as repair_router
    from app.api.fusion import router as fusion_router
    from app.api.v1.diagnosis_agent import router as diagnosis_agent_router
    from app.api.frequency import router as frequency_router
    from app.api.feedback import router as feedback_router
    from app.api.checkin import router as checkin_router
    from app.api.audit import router as audit_router
    from app.api.analytics import router as analytics_router
    from app.api.growth import router as growth_router
    from app.api.freemium import router as freemium_router
    from app.api.growth_enhanced import router as growth_enhanced_router
    from app.api.points import router as points_router
    from app.api.seo import router as seo_router
    from app.api.seo_public import (
        seo_knowledge_router,
        health_router,
        health_tools_router,
        en_knowledge_router,
        en_health_router,
        en_health_tools_router,
    )
    from app.api.health_tools import tools_public_router
    from app.api.geo_infra import geo_router
    from app.api.share_report import router as share_report_router
    from app.api.share_public import router as share_public_router
    from app.api.tiered_growth import router as tiered_growth_router
    from app.api.payment import router as payment_router
    from app.api.gdpr import router as gdpr_router

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
    app.include_router(axes_router, prefix="/api/v1/axes", tags=["八轴稳态"])
    app.include_router(repair_router, prefix="/api/v1/repair", tags=["细胞修复"])
    app.include_router(fusion_router, prefix="/api/v1/fusion", tags=["融合诊断"])
    app.include_router(diagnosis_agent_router, prefix="/api/v1/diagnosis", tags=["AI诊断Agent"])
    app.include_router(frequency_router, prefix="/api/v1/frequency", tags=["频率疗法"])
    app.include_router(feedback_router, prefix="/api/v1/feedback", tags=["用户反馈"])
    app.include_router(checkin_router, prefix="/api/v1/checkin", tags=["自测闭环"])
    app.include_router(audit_router, prefix="/api/v1/audit", tags=["运行时审计"])
    app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["行为分析"])
    app.include_router(growth_router, prefix="/api/v1/growth", tags=["推广系统"])
    app.include_router(freemium_router, prefix="/api/v1/freemium", tags=["积分门禁"])
    app.include_router(growth_enhanced_router, prefix="/api/v1/growth", tags=["推广系统"])
    app.include_router(points_router, prefix="/api/v1/points", tags=["积分系统"])
    app.include_router(seo_router, prefix="/api/v1/seo", tags=["SEO管理"])
    # SEO 公开页面
    app.include_router(seo_knowledge_router, prefix="/knowledge", tags=["SEO公开"])
    app.include_router(health_router, prefix="/health", tags=["SEO公开"])
    app.include_router(health_tools_router, prefix="/health-tools", tags=["SEO公开"])
    # 英文镜像路由：只为真实存在英文译本的页面返回 200（见 seo_public._en_payload）
    app.include_router(en_knowledge_router, prefix="/en/knowledge", tags=["SEO公开EN"])
    app.include_router(en_health_router, prefix="/en/health", tags=["SEO公开EN"])
    app.include_router(en_health_tools_router, prefix="/en/health-tools", tags=["SEO公开EN"])
    # 免费健康工具（SEO 引流核心）
    app.include_router(tools_public_router, prefix="/health-tools", tags=["免费工具"])
    # GEO 基础设施（llms.txt, ai.txt, robots.txt）
    app.include_router(geo_router, tags=["GEO"])
    # 分享报告（登录用户操作）
    app.include_router(share_report_router, prefix="/api/v1/reports", tags=["分享报告"])
    # 阶梯邀请 + 积分购买
    app.include_router(tiered_growth_router, prefix="/api/v1/growth", tags=["阶梯邀请 & 积分购买"])
    # 虎皮椒支付回调 + 状态查询
    app.include_router(payment_router, prefix="/api/v1/payment", tags=["支付"])
    # GDPR 合规（数据导出/删除/同意管理）
    app.include_router(gdpr_router, prefix="/api/v1/gdpr", tags=["GDPR"])
    # 公开分享页面（无需登录）
    app.include_router(share_public_router, tags=["公开分享"])

    # 智能体能力路由（GOAI 借鉴落地）
    # 注意：app/api/agent.py 内已写死 "/api/v1/agent/..." 全路径，
    # 故此处的 include_router 不能再传 prefix，否则会变成 /api/v1/api/v1/agent/...
    try:
        from app.api.agent import router as agent_router

        app.include_router(agent_router)
    except Exception as _agent_err:  # noqa: BLE001
        logger.warning(f"[AGENT] 智能体路由未加载（能力不可用，已跳过）: {_agent_err}")

    # 静态前端文件服务 (frontend/) - 带缓存控制
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    import os

    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    if os.path.isdir(frontend_dir):
        # 挂载 assets 目录为静态资源
        assets_dir = os.path.join(frontend_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir, html=False), name="frontend-assets")

        # 根路径 "/" 返回 index.html (SPA fallback) - 带无缓存头
        @app.get("/")
        async def serve_frontend():
            resp = FileResponse(os.path.join(frontend_dir, "index.html"))
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return resp

    # 静态资源缓存控制中间件 - 防止浏览器缓存旧版本 JS/CSS
    @app.middleware("http")
    async def add_cache_control(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and request.url.path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

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

# Lazy initialization: only create app when accessed, not on import
# This allows alembic/env.py and other scripts to import submodules
# without triggering the full FastAPI application setup
app = None


def get_app() -> FastAPI:
    """Get or create the FastAPI application instance."""
    global app
    if app is None:
        app = create_app()
    return app
