"""AI 诊断 Agent 路由 - 异步诊断任务触发与状态查询"""
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from loguru import logger

from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(tags=["AI诊断Agent"])


# ---------------------------------------------------------------------------
# 内存任务存储（生产环境应替换为 Redis / 数据库）
# ---------------------------------------------------------------------------

_task_store: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VariantInput(BaseModel):
    """基因变异输入"""
    gene_symbol: str = Field(..., description="基因符号，如 TP53")
    rsid: str = Field("", description="rsID，如 rs1042522")
    hgvs: str = Field("", description="HGVS 命名，如 NM_000546.5:c.215C>G")
    uniprot_id: str = Field("", description="UniProt ID，如 P04637")
    allele_frequency: float = Field(0, description="等位基因频率")
    variant_impact: str = Field("", description="变异影响描述")


class LabResultInput(BaseModel):
    """检验指标输入"""
    name: str = Field(..., description="指标名称")
    value: str | float = Field(..., description="指标值")
    unit: str = Field("", description="单位")
    reference_range: str = Field("", description="参考范围")
    is_abnormal: bool = Field(False, description="是否异常")


class DiagnosisAgentRequest(BaseModel):
    """AI 诊断 Agent 请求"""
    genes: list[VariantInput] = Field(default_factory=list, description="基因变异列表")
    lab_results: list[LabResultInput] = Field(default_factory=list, description="检验指标列表")
    tcm_symptoms: list[str] = Field(default_factory=list, description="中医症状列表")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/agent-run", status_code=status.HTTP_202_ACCEPTED)
async def run_diagnosis_agent(
    body: DiagnosisAgentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    触发 AI 诊断 Agent 运行。
    - 后台异步执行五层因果链分析
    - 返回 task_id 用于查询状态
    """
    task_id = str(uuid.uuid4())

    # 初始化任务状态
    _task_store[task_id] = {
        "task_id": task_id,
        "user_id": current_user.id,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": None,
    }

    # 将请求参数转为 dict
    user_data = {
        "user_id": current_user.id,
        "genes": [g.model_dump() for g in body.genes],
        "lab_results": [l.model_dump() for l in body.lab_results],
        "tcm_symptoms": body.tcm_symptoms,
    }

    # 启动后台任务
    asyncio.create_task(_run_diagnosis_task(task_id, user_data))

    from app.config import settings

    logger.info(f"诊断任务已启动 | task_id={task_id} | user_id={current_user.id}")

    resp = {
        "success": True,
        "task_id": task_id,
        "status": "pending",
        "message": "诊断任务已启动，请通过 agent-status 接口查询进度",
        "llm_ready": settings.llm_ready,
    }
    if not settings.llm_ready:
        resp["message"] = (
            "诊断任务已启动，但服务端尚未配置 AI 分析凭证，"
            "本次将只返回你已提交数据的结构化回显（不会生成 L4/L5）"
        )
    return resp


@router.get("/agent-status/{task_id}")
async def get_diagnosis_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    查询 AI 诊断任务状态。
    - pending: 排队中
    - running: 分析中
    - completed: 完成（含 result）
    - failed: 失败（含 error）
    """
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务 {task_id} 不存在",
        )

    # 权限检查：只能查询自己的任务
    if task["user_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该任务",
        )

    response = {
        "success": True,
        "task_id": task["task_id"],
        "status": task["status"],
        "created_at": task["created_at"],
    }

    if task["status"] == "completed":
        result = task["result"] or {}
        response["result"] = result
        # 顶层透出，前端据此做强提示：
        # analysis_status=ok 才是可信的个人分析；unavailable 时禁止当作个人报告展示
        response["analysis_status"] = result.get("analysis_status", "ok")
        response["is_demo"] = bool(result.get("is_demo", False))
        response["contains_only_user_data"] = bool(result.get("contains_only_user_data", False))
        if result.get("unavailable_reason"):
            response["unavailable_reason"] = result["unavailable_reason"]
    elif task["status"] == "failed":
        response["error"] = task["error"]

    return response


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------

async def _run_diagnosis_task(task_id: str, user_data: dict) -> None:
    """后台执行诊断任务"""
    _task_store[task_id]["status"] = "running"

    try:
        from app.services.diagnosis_agent import DiagnosisAgent

        agent = DiagnosisAgent()
        result = await agent.run_full_diagnosis(user_data)

        _task_store[task_id]["status"] = "completed"
        _task_store[task_id]["result"] = result
        logger.info(f"诊断任务完成 | task_id={task_id}")

    except Exception as exc:
        _task_store[task_id]["status"] = "failed"
        _task_store[task_id]["error"] = str(exc)
        logger.error(f"诊断任务失败 | task_id={task_id} | error={exc}")
