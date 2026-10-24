"""P1-2 周报闭环任务（2026-10-24）

设计：
- 每周一 07:00 扫描所有有活跃研究（≥ 30 天内至少 1 条快照）的用户
- 对每位用户：
    1. 拿每个活跃 study 的最近两周轨迹
    2. 计算逐轴 delta（本周 vs 上周）
    3. 挑 1-2 条最值得说的变化（变化幅度最大的轴）
    4. 组一条站内通知（category=weekly_report, action_url=/changes）
- 幂等：同一 study 同一天最多 1 条周报（extra_data.week_start 去重）

失败隔离：单个用户失败不影响其他人；日志记录，任务整体仍返回成功计数。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import json

from loguru import logger

from app.worker import celery_app


def _compute_axis_delta(snapshots: list[dict]) -> dict[str, float | None]:
    """给定一个 study 的最近 N 条快照（含 axis_scores），计算每轴的 delta。

    snapshots: list of {"date": "YYYY-MM-DD", "axis_scores": {A: {score, ...}, ...}}
    返回: {"A": 2.5, "B": -1.0, ...}  # 本周均分 - 上周均分（本周 = 后 3 天，上周 = 前 7 天）
    """
    if not snapshots:
        return {}

    # 按日期排序
    ordered = sorted(snapshots, key=lambda s: s.get("date") or "")
    n = len(ordered)
    # 至少要有 2 天数据才有意义
    if n < 2:
        return {}

    # 后 30% 作为"本周"，前 70% 作为"上周"
    split = max(1, n - max(1, n // 3))
    prev_window = ordered[:split]
    curr_window = ordered[split:]

    deltas: dict[str, float | None] = {}
    axes_seen: set[str] = set()
    for s in ordered:
        for ax in (s.get("axis_scores") or {}).keys():
            axes_seen.add(ax)

    for ax in sorted(axes_seen):
        prev_scores = []
        curr_scores = []
        for s in prev_window:
            v = (s.get("axis_scores") or {}).get(ax)
            if v and v.get("measured") and v.get("score") is not None:
                prev_scores.append(float(v["score"]))
        for s in curr_window:
            v = (s.get("axis_scores") or {}).get(ax)
            if v and v.get("measured") and v.get("score") is not None:
                curr_scores.append(float(v["score"]))
        if prev_scores and curr_scores:
            prev_mean = sum(prev_scores) / len(prev_scores)
            curr_mean = sum(curr_scores) / len(curr_scores)
            deltas[ax] = round(curr_mean - prev_mean, 2)
        else:
            deltas[ax] = None

    return deltas


def _top_changes(deltas: dict[str, float | None], top_k: int = 2) -> list[tuple[str, float]]:
    """从 deltas 中挑 top_k 个 |delta| 最大的轴。"""
    valid = [(ax, d) for ax, d in deltas.items() if d is not None and abs(d) >= 1.0]
    valid.sort(key=lambda x: abs(x[1]), reverse=True)
    return valid[:top_k]


def _build_report_body(study_name: str, snapshots_count: int, top_changes: list[tuple[str, float]]) -> str:
    """构造面向用户的周报内容（走 plain text，避免 HTML 转义风险）。

    严格走 wellness 措辞——不出现"改善/治愈/疗效"，只说"变化/趋势"。
    """
    lines = [
        f"📊 {study_name} · 本周变化",
        f"",
        f"过去两周记录了 {snapshots_count} 条快照。变化最明显的轴：",
    ]
    if not top_changes:
        lines.append("  • 各轴变化都在 1 分以内，趋势平稳。")
    else:
        for ax, d in top_changes:
            arrow = "↑" if d > 0 else "↓"
            lines.append(f"  • {ax} 轴 {arrow} {abs(d)} 分")

    lines.extend([
        "",
        "→ 点开「我的变化」看完整对比与因果归因",
        "→ 数据仅供健康参考，非医疗结论",
    ])
    return "\n".join(lines)


@celery_app.task(bind=True, max_retries=0, default_retry_delay=300)
def generate_weekly_reports(task_self, days_back: int = 14, min_snapshots: int = 2, batch_limit: int = 200):
    """为所有活跃用户生成周报到站内通知。

    Args:
        days_back: 回顾窗口（默认 14 天）
        min_snapshots: 至少需要多少条快照才生成周报
        batch_limit: 单批最多处理多少用户（避免雪崩）
    """
    import asyncio
    return asyncio.run(_run_weekly_reports(days_back=days_back, min_snapshots=min_snapshots, batch_limit=batch_limit))


async def _run_weekly_reports(days_back: int, min_snapshots: int, batch_limit: int) -> dict:
    from sqlalchemy import select, and_, func, desc, distinct
    from sqlalchemy.orm import selectinload
    from app.database import SessionLocal
    from app.models.user import User
    from app.models.longitudinal import LongitudinalStudy, AxisSnapshot, InterventionEvent
    from app.models.notification import Notification

    db = SessionLocal()
    stats = {"users_scanned": 0, "reports_sent": 0, "skipped_no_data": 0, "skipped_recent": 0, "errors": 0}
    week_start = datetime.now(timezone.utc).date().isoformat()
    window_start = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()

    try:
        # 步骤 1：找出过去 days_back 天内有 ≥ min_snapshots 快照的 (user_id, study_id) 对
        result = await db.execute(
            select(AxisSnapshot.user_id, AxisSnapshot.study_id, func.count(AxisSnapshot.id))
            .where(
                AxisSnapshot.date >= window_start,
                AxisSnapshot.user_id.isnot(None),
            )
            .group_by(AxisSnapshot.user_id, AxisSnapshot.study_id)
            .having(func.count(AxisSnapshot.id) >= min_snapshots)
            .limit(batch_limit)
        )
        study_rows = result.all()

        if not study_rows:
            logger.info("[WeeklyReport] No studies with ≥{} snapshots in the last {}d".format(min_snapshots, days_back))
            return stats

        # 批量拉取 study 名
        study_ids = [sid for _, sid, _ in study_rows]
        studies = (await db.execute(
            select(LongitudinalStudy).where(LongitudinalStudy.id.in_(study_ids))
        )).scalars().all()
        study_name_map = {s.id: (s.name or f"study {s.id[:8]}") for s in studies}

        sent_ids = set()
        for user_id, study_id, snap_count in study_rows:
            stats["users_scanned"] += 1
            try:
                # 幂等检查：同一用户+study 本周已发过则跳过
                recent = await db.execute(
                    select(Notification.id).where(
                        Notification.user_id == user_id,
                        Notification.category == "weekly_report",
                        Notification.created_at >= datetime.now(timezone.utc).date(),
                    )
                )
                recent_ids = {r[0] for r in recent.all()}
                already_for_study = any(
                    f"study_id:{study_id}" in (row_extra or "")
                    for row_extra in [
                        getattr(n, "extra_data", None) or ""
                        for n in []
                    ]
                )
                # 简单些：拉当天该用户所有 weekly_report 通知的 extra_data
                today_reports = (await db.execute(
                    select(Notification.extra_data).where(
                        Notification.user_id == user_id,
                        Notification.category == "weekly_report",
                        Notification.created_at >= datetime.now(timezone.utc).date().replace(tzinfo=timezone.utc),
                    )
                )).scalars().all()
                for extra in today_reports:
                    try:
                        obj = json.loads(extra or "{}")
                        if obj.get("study_id") == study_id:
                            stats["skipped_recent"] += 1
                            raise Exception("__skip__")
                    except json.JSONDecodeError:
                        pass

                # 拉该 study 最近窗口内的快照
                snaps = (await db.execute(
                    select(AxisSnapshot).where(
                        AxisSnapshot.study_id == study_id,
                        AxisSnapshot.date >= window_start,
                    ).order_by(AxisSnapshot.date.asc())
                )).scalars().all()

                snaps_list = [
                    {
                        "date": s.date,
                        "axis_scores": s.axis_scores or {},
                    }
                    for s in snaps
                ]
                if len(snaps_list) < min_snapshots:
                    stats["skipped_no_data"] += 1
                    continue

                deltas = _compute_axis_delta(snaps_list)
                top_changes = _top_changes(deltas, top_k=2)
                body = _build_report_body(study_name_map.get(study_id, study_id[:8]), len(snaps_list), top_changes)

                # 拉过去 days_back 天的干预数量
                intervention_count = (await db.execute(
                    select(func.count(InterventionEvent.id)).where(
                        InterventionEvent.study_id == study_id,
                        InterventionEvent.started_at >= datetime.now(timezone.utc).date().replace(tzinfo=timezone.utc) - timedelta(days=days_back),
                    )
                )).scalar() or 0

                notification = Notification(
                    user_id=user_id,
                    category="weekly_report",
                    title=f"📊 本周变化 · {study_name_map.get(study_id, study_id[:8])}",
                    content=body,
                    severity="info",
                    action_url="/changes",
                    action_label="查看我的变化",
                    extra_data=json.dumps({
                        "study_id": study_id,
                        "week_start": week_start,
                        "days_back": days_back,
                        "snapshots_count": len(snaps_list),
                        "interventions_count": intervention_count,
                        "deltas": deltas,
                        "top_changes": [[ax, d] for ax, d in top_changes],
                    }),
                )
                db.add(notification)
                await db.commit()
                stats["reports_sent"] += 1
            except Exception as exc:
                if str(exc) == "__skip__":
                    continue
                stats["errors"] += 1
                logger.warning(f"[WeeklyReport] user={user_id} study={study_id} failed: {exc}")
                await db.rollback()

        return stats
    finally:
        await db.close()


@celery_app.task(bind=True, max_retries=0)
def generate_weekly_report_for_user(task_self, user_id: str, study_id: str, days_back: int = 14):
    """单个用户+单个 study 的周报（供前端手动触发）。

    失败返回错误详情而不抛异常——前端需要展示原因。
    """
    import asyncio
    try:
        result = asyncio.run(_generate_single_user_report(user_id, study_id, days_back))
        return {"success": True, "data": result}
    except Exception as exc:
        logger.error(f"[WeeklyReport] manual generate failed for user={user_id} study={study_id}: {exc}")
        return {"success": False, "detail": str(exc)}


async def _generate_single_user_report(user_id: str, study_id: str, days_back: int) -> dict:
    from sqlalchemy import select, func, and_
    from app.database import SessionLocal
    from app.models.longitudinal import LongitudinalStudy, AxisSnapshot, InterventionEvent
    from app.models.notification import Notification

    db = SessionLocal()
    try:
        study = (await db.execute(
            select(LongitudinalStudy).where(
                LongitudinalStudy.id == study_id,
                LongitudinalStudy.user_id == user_id,
            )
        )).scalar_one_or_none()
        if not study:
            raise Exception("Study not found or not owned")

        window_start = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
        snaps = (await db.execute(
            select(AxisSnapshot).where(
                AxisSnapshot.study_id == study_id,
                AxisSnapshot.date >= window_start,
            ).order_by(AxisSnapshot.date.asc())
        )).scalars().all()
        if len(snaps) < 2:
            raise Exception("Not enough snapshots in the window (need ≥ 2)")

        snaps_list = [{"date": s.date, "axis_scores": s.axis_scores or {}} for s in snaps]
        deltas = _compute_axis_delta(snaps_list)
        top_changes = _top_changes(deltas, top_k=2)

        intervention_count = (await db.execute(
            select(func.count(InterventionEvent.id)).where(
                InterventionEvent.study_id == study_id,
                InterventionEvent.started_at >= datetime.now(timezone.utc).date().replace(tzinfo=timezone.utc) - timedelta(days=days_back),
            )
        )).scalar() or 0

        # 挑一个单点建议：变化最大的轴，如果为负则建议关注
        focus_axis = top_changes[0][0] if top_changes else None

        return {
            "study_id": study_id,
            "study_name": study.name,
            "week_start": (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat(),
            "week_end": datetime.now(timezone.utc).date().isoformat(),
            "days_back": days_back,
            "snapshots_count": len(snaps_list),
            "interventions_count": intervention_count,
            "axis_deltas": deltas,
            "top_changes": [[ax, d] for ax, d in top_changes],
            "focus_axis": focus_axis,
            "summary": body := _build_report_body(study.name, len(snaps_list), top_changes),
        }
    finally:
        await db.close()
