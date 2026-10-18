"""
feedback_loop.py — 用户反馈闭环。

收集用户对推荐结果的反馈（采纳/拒绝/修正），写入案例库，
支持按准确率趋势回测和弱项识别。

对外 API:
    collect_feedback(user_id, case_id, action, comment=None, corrected=None)
    get_user_history(user_id)
    get_feedback_stats()
    top_weak_items(n=10)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
FB_PATH = ROOT / "data" / "feedback_db.json"


@dataclass
class Feedback:
    user_id: str
    case_id: str
    action: str  # accept | reject | correct
    comment: str | None = None
    corrected_text: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Feedback:
        return cls(**d)


@dataclass
class FeedbackStats:
    total: int = 0
    accept: int = 0
    reject: int = 0
    correct: int = 0
    accuracy_pct: float = 0.0
    by_axis: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _load() -> list[Feedback]:
    if not FB_PATH.exists():
        return []
    try:
        with open(FB_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [Feedback.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError):
        return []


def _save(feeds: list[Feedback]) -> None:
    FB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FB_PATH, "w", encoding="utf-8") as f:
        json.dump([fb.to_dict() for fb in feeds], f, ensure_ascii=False, indent=2)


def collect_feedback(
    user_id: str,
    case_id: str,
    action: str,
    comment: str | None = None,
    corrected_text: str | None = None,
) -> dict[str, Any]:
    """收集用户反馈，返回写入结果。"""
    action = action.lower()
    if action not in ("accept", "reject", "correct"):
        return {"status": "error", "error": f"Invalid action: {action}"}

    fb = Feedback(
        user_id=user_id,
        case_id=case_id,
        action=action,
        comment=comment,
        corrected_text=corrected_text,
    )
    feeds = _load()
    feeds.append(fb)
    _save(feeds)
    return {
        "status": "ok",
        "feedback_id": len(feeds) - 1,
        "action": action,
        "total": len(feeds),
    }


def get_user_history(user_id: str) -> list[dict]:
    """获取指定用户的历史反馈。"""
    feeds = _load()
    return [fb.to_dict() for fb in feeds if fb.user_id == user_id]


def get_feedback_stats() -> dict:
    """全局反馈统计。"""
    feeds = _load()
    stats = FeedbackStats(total=len(feeds))
    by_axis_total: dict[str, int] = {}

    for fb in feeds:
        if fb.action == "accept":
            stats.accept += 1
        elif fb.action == "reject":
            stats.reject += 1
        elif fb.action == "correct":
            stats.correct += 1
        # 按 case_id 前缀粗粒度统计 axis（如 case_id = "H_axis_001"）
        axis = fb.case_id.split("_")[0] if "_" in fb.case_id else "unknown"
        by_axis_total[axis] = by_axis_total.get(axis, 0) + 1

    if stats.total > 0:
        stats.accuracy_pct = round(
            (stats.accept + stats.correct) / stats.total * 100, 1
        )

    stats.by_axis = by_axis_total
    return stats.to_dict()


def top_weak_items(n: int = 10) -> list[dict]:
    """找出被 reject/correct 最多的 case，识别系统性弱项。"""
    feeds = _load()
    reject_count: dict[str, int] = {}
    for fb in feeds:
        if fb.action in ("reject", "correct"):
            reject_count[fb.case_id] = reject_count.get(fb.case_id, 0) + 1

    sorted_items = sorted(reject_count.items(), key=lambda x: -x[1])[:n]
    return [
        {"case_id": cid, "reject_count": cnt, "axis": cid.split("_")[0] if "_" in cid else "unknown"}
        for cid, cnt in sorted_items
    ]


def run_feedback_analysis(inputs: dict | None = None) -> dict[str, Any]:
    """
    Pipeline handler: 执行反馈分析。
    inputs 可选: {"user_id": ..., "case_id": ..., "action": ..., "comment": ..., "corrected_text": ...}
    如果有 action → 写入反馈；否则返回统计。
    """
    inputs = inputs or {}

    if "action" in inputs:
        return collect_feedback(
            user_id=inputs.get("user_id", "anonymous"),
            case_id=inputs.get("case_id", "unknown"),
            action=inputs.get("action", "accept"),
            comment=inputs.get("comment"),
            corrected_text=inputs.get("corrected_text"),
        )

    return {
        "status": "ok",
        "phase": "feedback_loop",
        "stats": get_feedback_stats(),
        "top_weak": top_weak_items(),
    }
