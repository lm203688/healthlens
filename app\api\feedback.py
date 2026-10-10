"""
用户反馈收集 API
路由前缀: /api/v1/feedback
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

# 内存存储
_feedback_store = []
_effect_store = []


class SatisfactionFeedback(BaseModel):
    result_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5, description="满意度评分 1-5")
    feedback_text: Optional[str] = Field(None, max_length=1000)
    tags: Optional[List[str]] = None


class EffectTracking(BaseModel):
    result_id: Optional[str] = None
    metric_type: Optional[str] = Field(None, pattern="^(energy|sleep|mood|digestion)$")
    before_value: Optional[int] = Field(None, ge=1, le=10)
    after_value: Optional[int] = Field(None, ge=1, le=10)
    days_elapsed: Optional[int] = Field(None, ge=0, le=365)


@router.post("/satisfaction", summary="提交方案满意度评价")
async def submit_satisfaction(
    body: SatisfactionFeedback,
    current_user: Optional[User] = Depends(get_current_user),
):
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.id if current_user else None,
        "result_id": body.result_id,
        "rating": body.rating,
        "feedback_text": body.feedback_text,
        "tags": body.tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _feedback_store.append(entry)
    return {"success": True, "data": {"id": entry["id"]}, "message": "评价已提交，感谢反馈"}


@router.post("/effect", summary="提交效果追踪")
async def submit_effect(
    body: EffectTracking,
    current_user: Optional[User] = Depends(get_current_user),
):
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.id if current_user else None,
        "result_id": body.result_id,
        "metric_type": body.metric_type,
        "before_value": body.before_value,
        "after_value": body.after_value,
        "days_elapsed": body.days_elapsed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _effect_store.append(entry)
    return {"success": True, "data": {"id": entry["id"]}, "message": "效果追踪已记录"}


@router.get("/stats", summary="获取反馈统计")
async def get_feedback_stats(
    current_user: Optional[User] = Depends(get_current_user),
):
    if not _feedback_store and not _effect_store:
        return {
            "success": True,
            "data": {
                "total_ratings": 0,
                "average_rating": 0.0,
                "rating_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                "effect_records": 0,
                "average_improvement": 0.0,
                "improvement_rate": 0.0,
            },
        }

    ratings = [f["rating"] for f in _feedback_store]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for r in ratings:
        distribution[str(r)] = distribution.get(str(r), 0) + 1

    effects = _effect_store
    improvements = [e["after_value"] - e["before_value"] for e in effects]
    avg_improvement = round(sum(improvements) / len(improvements), 2) if improvements else 0.0
    positive = sum(1 for i in improvements if i > 0)
    improvement_rate = round(positive / len(improvements) * 100, 1) if improvements else 0.0

    return {
        "success": True,
        "data": {
            "total_ratings": len(_feedback_store),
            "average_rating": avg_rating,
            "rating_distribution": distribution,
            "effect_records": len(effects),
            "average_improvement": avg_improvement,
            "improvement_rate": improvement_rate,
        },
    }


@router.get("/list", summary="获取当前用户的反馈列表")
async def get_feedback_list(
    current_user: Optional[User] = Depends(get_current_user),
):
    user_id = current_user.id if current_user else None
    feedbacks = [f for f in _feedback_store if f.get("user_id") == user_id]
    effects = [e for e in _effect_store if e.get("user_id") == user_id]
    return {
        "success": True,
        "data": {
            "feedbacks": feedbacks,
            "effects": effects,
        },
    }
