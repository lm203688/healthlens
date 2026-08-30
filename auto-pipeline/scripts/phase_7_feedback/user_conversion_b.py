"""
B线：用户转化闭环
追踪用户注册→使用→付费的完整链路
计算留存率、转化率、方案效果评分
输出：conversion_funnel.json + 回写用户活跃度指标
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import (
    BASE_DIR,
    complete_phase,
    fail_phase,
    get_state,
    log,
    save_state,
    start_phase,
)

DB_URL_FALLBACK = "postgresql://healthlens:healthlens@localhost:5432/healthlens"


def _get_db_url():
    """优先级：环境变量 DATABASE_URL > config.database.url > 本地默认"""
    import os
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("database", {}).get("url", "")
        if url:
            return url
    except Exception:
        pass
    return DB_URL_FALLBACK


DB_URL = _get_db_url()


def get_user_metrics_from_db():
    """从数据库获取真实用户指标"""
    try:
        import asyncpg
    except ImportError:
        log("asyncpg未安装，无法读取真实用户数据")
        return None

    import asyncio

    async def _query():
        conn = None
        try:
            conn = await asyncpg.connect(DB_URL)
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)

            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            new_users_week = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at >= $1", week_ago
            )

            # 活跃用户（本周有检测记录）
            active_users_week = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM health_reports WHERE created_at >= $1",
                week_ago,
            ) or 0

            # 付费转化
            paid_users = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM point_orders WHERE payment_status = 'paid'"
            ) or 0

            # 本周付费
            paid_week = await conn.fetchval(
                "SELECT COUNT(*) FROM point_orders WHERE payment_status = 'paid' AND paid_at >= $1",
                week_ago,
            ) or 0

            # 漏斗数据
            registered = total_users or 0
            completed_profile = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE sleep_data IS NOT NULL OR body_data IS NOT NULL"
            ) or 0
            generated_report = await conn.fetchval("SELECT COUNT(*) FROM health_reports") or 0
            viewed_plan = await conn.fetchval(
                "SELECT COUNT(*) FROM health_reports WHERE plan IS NOT NULL"
            ) or 0
            purchased_points = paid_users

            # 留存率（简化：7日内有活动的用户 / 7日前注册的用户）
            d7_ago = now - timedelta(days=7)
            d30_ago = now - timedelta(days=30)
            users_before_d7 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at <= $1", d7_ago
            ) or 0
            active_after_d7 = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM health_reports WHERE created_at >= $1",
                d7_ago,
            ) or 0
            retention_d7 = round(active_after_d7 / max(users_before_d7, 1) * 100, 1)

            users_before_d30 = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE created_at <= $1", d30_ago
            ) or 0
            active_after_d30 = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM health_reports WHERE created_at >= $1",
                d30_ago,
            ) or 0
            retention_d30 = round(active_after_d30 / max(users_before_d30, 1) * 100, 1)

            await conn.close()

            return {
                "total_users": registered,
                "new_users_week": new_users_week or 0,
                "active_users_week": active_users_week,
                "retention_rate_d7": retention_d7,
                "retention_rate_d30": retention_d30,
                "paid_conversion_rate": round(paid_users / max(registered, 1) * 100, 1),
                "points_purchased_week": paid_week,
                "health_reports_generated": generated_report,
                "funnel": {
                    "registered": registered,
                    "completed_profile": completed_profile,
                    "generated_report": generated_report,
                    "viewed_plan": viewed_plan,
                    "purchased_points": purchased_points,
                },
                "data_source": "real_database",
            }
        except Exception as e:
            log(f"数据库查询失败: {e}")
            return None
        finally:
            if conn:
                try:
                    await conn.close()
                except Exception:
                    pass

    return asyncio.run(_query())


def get_user_metrics_fallback():
    """降级：返回零值占位数据（标记为 mock）"""
    return {
        "total_users": 0,
        "new_users_week": 0,
        "active_users_week": 0,
        "retention_rate_d7": 0,
        "retention_rate_d30": 0,
        "paid_conversion_rate": 0,
        "points_purchased_week": 0,
        "health_reports_generated": 0,
        "funnel": {
            "registered": 0,
            "completed_profile": 0,
            "generated_report": 0,
            "viewed_plan": 0,
            "purchased_points": 0,
        },
        "data_source": "mock_zero",
    }


def analyze_plan_effectiveness():
    """分析方案效果追踪数据"""
    return {
        "plans_generated": 0,
        "plans_with_follow_up": 0,
        "avg_improvement_score": 0,
        "top_improving_category": None,
        "improvement_by_category": {},
        "data_source": "placeholder",
    }


def calculate_funnel_dropoffs(funnel):
    """计算转化漏斗各环节的流失率"""
    stages = list(funnel.keys())
    dropoffs = []
    for i in range(len(stages) - 1):
        curr = funnel[stages[i]]
        next_s = funnel[stages[i + 1]]
        if curr > 0:
            rate = round((1 - next_s / curr) * 100, 1)
            dropoffs.append({"from": stages[i], "to": stages[i + 1], "dropoff_rate": rate, "users_lost": curr - next_s})
    return dropoffs


def run():
    phase = "user_conversion_b"
    try:
        start_phase(phase)

        # 获取用户指标（优先真实数据，降级到零值占位）
        metrics = get_user_metrics_from_db() or get_user_metrics_fallback()
        plan_effect = analyze_plan_effectiveness()

        funnel = metrics.get("funnel", {})
        dropoffs = calculate_funnel_dropoffs(funnel)

        # 找出最大流失点
        max_dropoff = max(dropoffs, key=lambda x: x["dropoff_rate"]) if dropoffs else None

        state = get_state()
        state.setdefault("feedback_metrics", {})["user_conversion"] = {
            "checked_at": datetime.now().isoformat(),
            "data_source": metrics.get("data_source", "unknown"),
            "weekly_active_rate": round(metrics["active_users_week"] / max(metrics["total_users"], 1) * 100, 1),
            "d7_retention": metrics["retention_rate_d7"],
            "paid_conversion": metrics["paid_conversion_rate"],
            "biggest_dropoff": max_dropoff,
            "plan_effectiveness": plan_effect["avg_improvement_score"]
        }
        save_state(state)

        report = {
            "report_id": f"conversion_b_{datetime.now().strftime('%Y%m%d')}",
            "generated_at": datetime.now().isoformat(),
            "data_source": metrics.get("data_source", "unknown"),
            "user_metrics": metrics,
            "plan_effectiveness": plan_effect,
            "funnel_dropoffs": dropoffs,
            "biggest_dropoff": max_dropoff,
            "recommendations": _generate_recommendations(metrics, plan_effect, max_dropoff)
        }

        output_file = f"reports/analysis/{datetime.now().strftime('%Y-%m-%d')}_conversion_b.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(phase, output_file=output_file, items_processed=len(dropoffs))
        log(f"B线转化分析完成 (数据源={metrics.get('data_source')}): 7日留存 {metrics['retention_rate_d7']}%, 付费转化 {metrics['paid_conversion_rate']}%")
        return True
    except Exception as e:
        fail_phase(phase, str(e))
        return False


def _generate_recommendations(metrics, plan_effect, max_dropoff):
    recs = []
    if metrics["retention_rate_d7"] < 40:
        recs.append({"type": "retention", "priority": "high", "action": "优化新用户引导流程，增加首日价值感知"})
    if metrics["paid_conversion_rate"] < 5:
        recs.append({"type": "monetization", "priority": "high", "action": "优化积分套餐定价和购买体验"})
    if plan_effect["avg_improvement_score"] < 0.6:
        recs.append({"type": "plan_quality", "priority": "medium", "action": "优化个性化方案生成算法"})
    if max_dropoff and max_dropoff["dropoff_rate"] > 50:
        recs.append({"type": "funnel", "priority": "high", "action": f"修复最大流失点: {max_dropoff['from']}→{max_dropoff['to']} ({max_dropoff['dropoff_rate']}%流失)"})
    return recs


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
