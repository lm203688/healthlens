"""
E线：资金闭环
自动核算收支、计算单位经济效益、成本预警、扩容提醒、再投资建议
从数据库读取真实订单数据，不再使用模拟数据
输出：finance_report.json
"""
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import get_state, save_state, BASE_DIR, log, start_phase, complete_phase, fail_phase

# 数据库连接配置（与 .env 一致）
DB_URL = "postgresql://healthlens:healthlens@localhost:5432/healthlens"


async def get_real_revenue_data():
    """从数据库读取真实收入数据"""
    try:
        import asyncpg
    except ImportError:
        log("asyncpg未安装，无法读取真实订单数据")
        return {
            "data_source": "db_unavailable",
            "weekly": {"revenue": 0, "paid_orders": 0, "paying_users": 0, "new_users": 0, "mock_test_orders": 0},
            "all_time": {"revenue": 0, "paid_orders": 0, "paying_users": 0},
            "total_users": 0,
            "package_distribution": [],
        }

    conn = None
    try:
        conn = await asyncpg.connect(DB_URL)

        # 本周真实付费订单（排除mock测试订单）
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        # 本周已支付的真实订单
        weekly_paid = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as order_count,
                COUNT(DISTINCT user_id) as paying_users,
                COALESCE(SUM(price_cny), 0) as total_revenue
            FROM point_orders
            WHERE payment_status = 'paid'
              AND payment_method IN ('xunhu', 'wechat', 'alipay')
              AND paid_at >= $1
            """,
            week_ago,
        )

        # 全部历史真实付费订单
        all_time_paid = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as order_count,
                COUNT(DISTINCT user_id) as paying_users,
                COALESCE(SUM(price_cny), 0) as total_revenue
            FROM point_orders
            WHERE payment_status = 'paid'
              AND payment_method IN ('xunhu', 'wechat', 'alipay')
            """
        )

        # 本周新增用户
        new_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at >= $1",
            week_ago,
        )

        # 总注册用户
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")

        # 本周mock订单（测试用，不计入收入）
        mock_orders = await conn.fetchval(
            """
            SELECT COUNT(*) FROM point_orders
            WHERE payment_status = 'paid'
              AND payment_method = 'mock'
              AND paid_at >= $1
            """,
            week_ago,
        )

        # 套餐分布
        package_dist = await conn.fetch(
            """
            SELECT package_code, COUNT(*) as cnt, SUM(price_cny) as revenue
            FROM point_orders
            WHERE payment_status = 'paid'
              AND payment_method IN ('xunhu', 'wechat', 'alipay')
            GROUP BY package_code
            """
        )

        await conn.close()

        return {
            "data_source": "real_database",
            "weekly": {
                "revenue": float(weekly_paid["total_revenue"] or 0),
                "paid_orders": weekly_paid["order_count"],
                "paying_users": weekly_paid["paying_users"],
                "new_users": new_users,
                "mock_test_orders": mock_orders,
            },
            "all_time": {
                "revenue": float(all_time_paid["total_revenue"] or 0),
                "paid_orders": all_time_paid["order_count"],
                "paying_users": all_time_paid["paying_users"],
            },
            "total_users": total_users,
            "package_distribution": [
                {"package": r["package_code"], "orders": r["cnt"], "revenue": float(r["revenue"] or 0)}
                for r in package_dist
            ],
        }

    except Exception as e:
        log(f"数据库查询失败: {e}")
        if conn:
            try:
                await conn.close()
            except Exception:
                pass
        return {
            "data_source": "db_error",
            "error": str(e),
            "weekly": {"revenue": 0, "paid_orders": 0, "paying_users": 0, "new_users": 0, "mock_test_orders": 0},
            "all_time": {"revenue": 0, "paid_orders": 0, "paying_users": 0},
            "total_users": 0,
            "package_distribution": [],
        }


def get_cost_data():
    """获取成本数据（真实配置）"""
    return {
        "costs": {
            "server_tencent_cloud": {"amount": 65, "type": "fixed_monthly", "plan": "2核2G轻量"},
            "domain_ssl": {"amount": 0, "type": "free", "provider": "Cloudflare"},
            "api_calls": {"amount": 12.5, "type": "variable", "usage": "3500 calls"},
            "storage": {"amount": 0, "type": "free_within_limit"},
        },
        "budget_limit": {"monthly": 500, "alert_threshold": 0.8},
    }


def calculate_unit_economics(real_data, cost_data, metrics):
    """计算单位经济效益（基于真实数据）"""
    weekly_revenue = real_data["weekly"]["revenue"]
    weekly_cost = sum(c["amount"] for c in cost_data["costs"].values())
    paying_users = real_data["weekly"]["paying_users"]
    active_users = metrics.get("active_users_week", real_data.get("total_users", 0)) if metrics else real_data.get("total_users", 0)

    return {
        "weekly_revenue": round(weekly_revenue, 2),
        "weekly_cost": round(weekly_cost, 2),
        "weekly_profit": round(weekly_revenue - weekly_cost, 2),
        "monthly_revenue_est": round(weekly_revenue * 4.3, 2),
        "monthly_cost_est": round(weekly_cost * 4.3, 2),
        "monthly_profit_est": round((weekly_revenue - weekly_cost) * 4.3, 2),
        "arpu_paying": round(weekly_revenue / max(paying_users, 1), 2) if paying_users > 0 else 0,
        "arpu_all": round(weekly_revenue / max(active_users, 1), 2) if active_users > 0 else 0,
        "unit_economics": "positive" if weekly_revenue > weekly_cost else "negative",
        "all_time_revenue": round(real_data["all_time"]["revenue"], 2),
        "all_time_paid_orders": real_data["all_time"]["paid_orders"],
    }


def check_cost_alerts(cost_data, real_data):
    """检查成本预警"""
    alerts = []
    total_monthly_cost = sum(c["amount"] * 4.3 for c in cost_data["costs"].values())
    budget = cost_data["budget_limit"]["monthly"]

    if total_monthly_cost > budget * cost_data["budget_limit"]["alert_threshold"]:
        alerts.append({
            "type": "budget_warning",
            "message": f"月成本估算 ¥{total_monthly_cost:.0f} 超过预算预警线(¥{budget * 0.8:.0f})",
            "severity": "warning",
        })

    api_cost = cost_data["costs"]["api_calls"]["amount"]
    if api_cost > 20:
        alerts.append({"type": "api_cost_high", "message": f"API周调用成本 ¥{api_cost}，需优化调用频率", "severity": "medium"})

    # 零收入预警
    if real_data["weekly"]["revenue"] == 0 and real_data["all_time"]["revenue"] == 0:
        alerts.append({
            "type": "zero_revenue",
            "message": "真实收入为零：前端缺少购买积分页面，用户无法付费。需尽快上线购买入口。",
            "severity": "critical",
        })

    return alerts


def check_infrastructure_needs(cost_data, real_data):
    """检查基础设施扩容需求"""
    needs = []
    total_users = real_data.get("total_users", 0)

    if total_users > 500:
        needs.append({"resource": "server", "current": "2核2G", "suggested": "4核4G", "reason": "用户量超过500", "est_cost": "150-200元/月"})

    api_usage = cost_data["costs"]["api_calls"]["usage"]
    api_usage_num = 0
    if api_usage:
        import re
        num_match = re.search(r'[\d,]+', str(api_usage))
        if num_match:
            api_usage_num = int(num_match.group().replace(",", ""))
    if api_usage_num > 10000:
        needs.append({"resource": "api_quota", "reason": "API调用接近免费额度上限"})

    needs.append({"resource": "ssl_certificate", "status": "Cloudflare免费", "next_check": "2026-10-27", "note": "域名备案后需迁移到自有证书"})

    return needs


def run():
    phase = "finance_e"
    try:
        start_phase(phase)

        # 从数据库获取真实收入数据
        real_data = asyncio.run(get_real_revenue_data())
        cost_data = get_cost_data()

        state = get_state()
        metrics = state.get("feedback_metrics", {}).get("user_conversion", {})

        economics = calculate_unit_economics(real_data, cost_data, metrics)
        alerts = check_cost_alerts(cost_data, real_data)
        infra_needs = check_infrastructure_needs(cost_data, real_data)

        state.setdefault("feedback_metrics", {})["finance"] = {
            "checked_at": datetime.now().isoformat(),
            "weekly_profit": economics["weekly_profit"],
            "monthly_profit_est": economics["monthly_profit_est"],
            "unit_economics": economics["unit_economics"],
            "all_time_revenue": economics["all_time_revenue"],
            "alerts": len(alerts),
            "data_source": real_data["data_source"],
        }
        save_state(state)

        # 生成建议
        if real_data["weekly"]["revenue"] == 0:
            recommendations = [
                "紧急：前端缺少购买积分页面，用户无法付费，需立即上线购买入口",
                "确认虎皮椒支付通道端到端可用（选套餐→扫码→回调→积分到账）",
                "在用户消耗免费积分后触发购买引导",
            ]
        elif economics["unit_economics"] == "positive" and len(alerts) == 0:
            recommendations = ["维持现状，继续积累用户基数"]
        else:
            recommendations = ["优化API调用频率降低成本"] + [f"扩容建议: {n['resource']} - {n['reason']}" for n in infra_needs]

        report = {
            "report_id": f"finance_e_{datetime.now().strftime('%Y%m%d')}",
            "generated_at": datetime.now().isoformat(),
            "data_source": real_data["data_source"],
            "real_revenue_data": real_data,
            "unit_economics": economics,
            "costs_detail": cost_data["costs"],
            "alerts": alerts,
            "infrastructure_needs": infra_needs,
            "recommendations": recommendations,
        }

        output_file = f"reports/analysis/{datetime.now().strftime('%Y-%m-%d')}_finance_e.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(phase, output_file=output_file, items_processed=1, alerts=len(alerts))
        log(
            f"E线资金核算完成: 周收入 ¥{economics['weekly_revenue']}(真实), "
            f"周成本 ¥{economics['weekly_cost']}, 周利润 ¥{economics['weekly_profit']}, "
            f"累计收入 ¥{economics['all_time_revenue']}, 数据源={real_data['data_source']}"
        )
        return True
    except Exception as e:
        fail_phase(phase, str(e))
        return False


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
