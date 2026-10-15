"""
健康信号拦截中间件
==================

HealthLens 是 wellness（健康管理）平台，不是医疗诊断系统。
但用户可能输入需要立即关注的健康信号（如胸痛、呼吸困难）。
此中间件在请求进入业务逻辑前检查文本字段，发现紧急信号时直接拦截。

这不是"医疗急症诊断"，而是"健康护栏"——
确保平台在用户可能面临紧急状况时不误导、不延误。
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.emergency_interceptor import check_emergency

# 需要检查文本字段的 API 路径（按路径前缀匹配）
# 注意：agent 家族端点必须纳入——用户自由文本输入的主要入口
PROTECTED_PATHS = [
    "/api/v1/axes/assess",       # 八轴评估
    "/api/v1/diagnosis/analyze", # AI 诊断分析
    "/api/v1/frequency",         # 频率分析
    "/api/v1/repair",            # 修复方案
    "/api/v1/goals",             # 目标管理
    "/api/v1/records",           # 健康记录
    "/api/v1/agent/",            # Agent 对话（team/fusion 等自由文本入口）
    "/api/v1/chat",              # 单轮对话
]

# 需要检查的文本字段名（按字段名匹配）
TEXT_FIELDS = [
    "symptom_description",
    "symptoms",
    "notes",
    "text",
    "description",
    "content",
    "feedback_text",
    "reason",
    "note",
    "user_input",                # Agent team/fusion 入口
    "message",                   # 通用聊天消息
    "query",                     # 查询类入口
]


def _extract_text_from_body(body: dict | None) -> str:
    """从请求体中提取所有文本字段拼接"""
    if not body or not isinstance(body, dict):
        return ""

    texts = []
    for field in TEXT_FIELDS:
        val = body.get(field)
        if isinstance(val, str) and val:
            texts.append(val)
        elif isinstance(val, list):
            # 处理列表字段（如 symptoms: ["胸痛", "胸闷"]）
            for item in val:
                if isinstance(item, str):
                    texts.append(item)

    return " ".join(texts)


def _check_biomarkers_for_emergency(body: dict | None):
    """
    检查生物标志物是否有危急值（需要立即关注）。
    返回命中的 CriticalValueHit 列表；空列表表示无命中。

    M10 P0-3：由硬编码 3 项（glucose/hba1c）改为表驱动 24 项危急值表，
    并支持任意嵌套路径（biomarkers/metrics/indicators）。
    原实现只查 body 顶层，导致八轴评估 `/axes/assess` 的 UserProfile
    输入（指标在 biomarkers 嵌套字典内）完全不生效——主入口被绕过。

    这是「健康护栏」，不是诊断：命中即引导就医，不给出诊断结论。
    """
    from app.lib.critical_values import check_critical_values
    return check_critical_values(body)


async def emergency_interceptor_middleware(request: Request, call_next):
    """
    健康信号拦截中间件

    在请求进入业务逻辑前检查：
    1. 文本字段是否包含紧急关键词
    2. 生物标志物是否有极端值

    如果发现需要立即关注的信号，直接返回引导信息，不进入业务逻辑。
    """
    # 只检查受保护的路径
    path = request.url.path
    should_check = any(path.startswith(p) for p in PROTECTED_PATHS)

    if not should_check:
        return await call_next(request)

    # 读取请求体
    try:
        body = await request.json()
    except Exception:
        body = None

    # 检查文本字段
    text = _extract_text_from_body(body)
    if text:
        result = check_emergency(text)
        if result.is_emergency:
            logger.warning(
                f"Emergency signal detected in {path}: {result.signal.category} - {result.signal.keywords}"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "code": "emergency_signal_detected",
                    "message": "检测到需要立即关注的健康信号",
                    "guidance": result.guidance,
                    "category": result.signal.category if result.signal else None,
                    "keywords": result.signal.keywords if result.signal else None,
                },
            )

    # 检查生物标志物危急值（表驱动 24 项，支持嵌套路径）
    if body:
        crit_hits = _check_biomarkers_for_emergency(body)
        if crit_hits:
            # 留痕：记录触发的具体指标与阈值，便于事后审计与复盘
            logger.warning(
                f"Critical biomarker value detected in {path}: "
                f"{[(h.label, h.direction, h.value, f'阈值{h.threshold}{h.unit}') for h in crit_hits]}"
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "code": "extreme_biomarker_value",
                    "message": "检测到需要立即关注的异常指标",
                    "guidance": "您的检测指标存在极端值，建议立即咨询医疗专业人员。HealthLens 是健康管理平台，不提供医疗诊断。",
                    "critical_values": [h.as_dict() for h in crit_hits],
                    "category": "生物标志物危急值",
                },
            )

    return await call_next(request)
