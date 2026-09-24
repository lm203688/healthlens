"""
合规与用户同意 API

端点：
- GET    /api/v1/compliance/policies      — 列出所有合规政策
- GET    /api/v1/compliance/policies/{id} — 获取政策详情
- POST   /api/v1/compliance/consent       — 记录用户同意
- GET    /api/v1/compliance/consent/{uid} — 查询用户同意状态

覆盖：隐私政策 / 服务条款 / 数据处理同意 / 未成年人保护
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent
CONSENT_DIR = ROOT / ".consent_data"
CONSENT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/compliance", tags=["合规与同意"])

# ---------------------------------------------------------------------------
# 政策定义（版本化管理）
# ---------------------------------------------------------------------------

_POLICIES = [
    {
        "id": "privacy_v1",
        "title": "隐私政策",
        "version": "1.0.0",
        "effective_date": "2026-01-01",
        "summary": "说明健康数据的收集、使用、存储、共享和删除方式。HealthLens 不对用户健康数据做商业化再利用。",
        "sections": [
            "数据收集范围", "数据使用目的", "数据存储与加密",
            "数据共享与第三方", "用户权利（访问/更正/删除）", "数据保留期限",
        ],
    },
    {
        "id": "terms_v1",
        "title": "服务条款",
        "version": "1.0.0",
        "effective_date": "2026-01-01",
        "summary": "HealthLens 提供健康评估与健康建议服务，不构成医疗诊断或治疗建议。用户需对自身健康决策负责。",
        "sections": [
            "服务性质与范围", "免责声明（非医疗诊断）", "用户责任",
            "知识产权", "服务变更与终止", "责任限制",
        ],
    },
    {
        "id": "data_processing_v1",
        "title": "数据处理同意",
        "version": "1.0.0",
        "effective_date": "2026-01-01",
        "summary": "用户同意 HealthLens 对其健康数据（体质/症状/基因通路得分/外部数据连接器数据）做脱敏后处理，用于健康评估与改进服务。",
        "sections": [
            "处理的数据类型", "处理方式（脱敏/聚合/匿名化）",
            "处理目的", "用户撤回权", "数据删除流程",
        ],
    },
    {
        "id": "minor_protection_v1",
        "title": "未成年人保护",
        "version": "1.0.0",
        "effective_date": "2026-01-01",
        "summary": "HealthLens 不面向 14 岁以下未成年人提供服务。14-18 岁用户需监护人同意。",
        "sections": [
            "年龄限制", "监护人同意流程", "未成年人数据特殊保护",
            "监护人查询与删除权",
        ],
    },
]


class ConsentRequest(BaseModel):
    user_id: str
    policy_ids: list[str]
    ip_address: str | None = None
    user_agent: str | None = None


class ConsentResponse(BaseModel):
    status: str
    user_id: str
    consented_at: str
    policies: list[str]


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/policies")
async def api_list_policies():
    """列出所有合规政策。"""
    return {"policies": _POLICIES}


@router.get("/policies/{policy_id}")
async def api_get_policy(policy_id: str):
    """获取单个政策详情。"""
    for p in _POLICIES:
        if p["id"] == policy_id:
            return p
    raise HTTPException(404, f"政策 '{policy_id}' 不存在")


@router.post("/consent", response_model=ConsentResponse)
async def api_record_consent(req: ConsentRequest):
    """记录用户同意。"""
    # 校验 policy_id
    valid_ids = {p["id"] for p in _POLICIES}
    for pid in req.policy_ids:
        if pid not in valid_ids:
            raise HTTPException(400, f"无效政策 ID: {pid}")

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "user_id": req.user_id,
        "policies": req.policy_ids,
        "consented_at": now,
        "ip_address": req.ip_address,
        "user_agent": req.user_agent,
    }

    # 持久化（简单文件存储，生产环境应换数据库）
    path = CONSENT_DIR / f"{req.user_id}.json"
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, list):
            existing.append(record)
        else:
            existing = [existing, record]
    except (FileNotFoundError, json.JSONDecodeError):
        existing = [record]

    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return ConsentResponse(
        status="ok", user_id=req.user_id,
        consented_at=now, policies=req.policy_ids,
    )


@router.get("/consent/{user_id}")
async def api_get_consent(user_id: str):
    """查询用户同意状态。"""
    path = CONSENT_DIR / f"{user_id}.json"
    if not path.exists():
        return {"user_id": user_id, "consented": False, "records": []}
    records = json.loads(path.read_text(encoding="utf-8"))
    return {"user_id": user_id, "consented": True, "records": records}