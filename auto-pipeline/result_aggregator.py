"""
HealthLens 定时任务结果聚合器
收集所有定时任务的执行结果，生成统一态势简报

数据来源：
  1. auto-pipeline: pipeline_state.json + reports/ 目录下的JSON报告
  2. Celery: 通过API查询任务执行状态（未来扩展）
  3. Schedule: 通过本系统调度执行的报告任务

输出：
  - reports/unified_briefing/YYYY-MM-DD_briefing.json  (机器可读)
  - 控制台打印摘要 (人类可读)
  - 写入记忆系统 topics.md (跨会话持久化)
"""
import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "scripts" / "core"))

from state_manager import get_state, log
from task_registry import ALL_TASKS, get_task_schedule_summary


# ===== 报告目录 =====
REPORT_DIRS = {
    "intelligence": BASE_DIR / "reports" / "intelligence",
    "analysis": BASE_DIR / "reports" / "analysis",
    "deployed": BASE_DIR / "reports" / "deployed",
    "monthly": BASE_DIR / "reports" / "monthly",
    "quarterly": BASE_DIR / "reports" / "quarterly",
    "promotion": BASE_DIR / "reports" / "promotion",
}

# 记忆系统路径
MEMORY_DIR = Path(r"c:\Users\xing\.trae-cn\memory\projects\-c-Users-xing-Desktop-healthlens")
TODAY_STR = datetime.now().strftime("%Y%m%d")
TOPICS_FILE = MEMORY_DIR / TODAY_STR / "topics.md"


def load_pipeline_state():
    """加载 pipeline 状态"""
    return get_state()


def load_report(report_path):
    """加载单个JSON报告"""
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def find_latest_reports(days=7):
    """查找最近N天的所有报告文件"""
    reports = []
    cutoff = datetime.now() - timedelta(days=days)

    for dir_name, dir_path in REPORT_DIRS.items():
        if not dir_path.exists():
            continue
        for f in dir_path.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime >= cutoff:
                    reports.append({
                        "path": str(f),
                        "name": f.name,
                        "category": dir_name,
                        "modified": mtime.isoformat(),
                        "data": load_report(f),
                    })
            except Exception:
                pass

    return sorted(reports, key=lambda x: x["modified"], reverse=True)


def extract_key_metrics(state, reports):
    """从状态和报告中提取关键指标"""
    metrics = state.get("feedback_metrics", {})
    pipeline_id = state.get("pipeline_id", "unknown")
    pipeline_status = state.get("status", "unknown")

    # A线内容指标
    a_metrics = {
        "pipeline_id": pipeline_id,
        "status": pipeline_status,
        "phases_completed": sum(1 for p in state.get("phases", {}).values() if p.get("status") == "completed"),
        "phases_failed": sum(1 for p in state.get("phases", {}).values() if p.get("status") == "failed"),
        "approved_items": len(state.get("approved_queue", [])),
        "watch_items": len(state.get("watch_queue", [])),
        "deployed_items": len(state.get("deployment_history", [])),
        "content_pipeline": metrics.get("content_pipeline", {}),
    }

    # B线用户转化
    b_metrics = metrics.get("user_conversion", {})

    # C线数据资产
    c_metrics = metrics.get("data_asset", {})

    # D线推广
    d_metrics = metrics.get("promotion", {})

    # E线资金
    e_metrics = metrics.get("finance", {})

    # F线运维
    f_metrics = metrics.get("ops_health", {})

    return {
        "A_line_content": a_metrics,
        "B_line_conversion": b_metrics,
        "C_line_data": c_metrics,
        "D_line_promotion": d_metrics,
        "E_line_finance": e_metrics,
        "F_line_ops": f_metrics,
    }


def extract_manual_actions(metrics, reports):
    """从所有指标中提取需要手动解决的问题"""
    actions = []

    # B线：付费转化断裂
    b = metrics.get("B_line_conversion", {})
    if b:
        dropoff = b.get("biggest_dropoff", {})
        if dropoff.get("dropoff_rate", 0) > 60:
            actions.append({
                "priority": "high",
                "line": "B",
                "category": "付费转化",
                "issue": f"漏斗流失点 {dropoff.get('from')}→{dropoff.get('to')} 流失率 {dropoff.get('dropoff_rate')}%",
                "action": f"优化付费转化路径，{dropoff.get('users_lost', 0)}个用户在此流失",
                "auto_fixable": False,
            })

    # C线：数据过期
    c = metrics.get("C_line_data", {})
    if c:
        for report in reports:
            if report["category"] == "analysis" and "data_asset_c" in report["name"]:
                data = report.get("data", {})
                for issue in data.get("quality_issues", []):
                    if issue.get("issue") == "outdated":
                        actions.append({
                            "priority": "high",
                            "line": "C",
                            "category": "数据过期",
                            "issue": f"{issue['source']} 数据已过期 {issue.get('days_since_sync', '?')}天",
                            "action": f"触发 {issue['source']} 增量同步",
                            "auto_fixable": False,
                        })
                break

    # D线：废渠道
    d = metrics.get("D_line_promotion", {})
    if d:
        for report in reports:
            if report["category"] == "analysis" and "promotion_d" in report["name"]:
                data = report.get("data", {})
                for ch, info in data.get("channel_roi", {}).items():
                    if info.get("efficiency") == "paid_poor" or (info.get("cac", 0) == float("inf") if isinstance(info.get("cac"), (int, float)) else False):
                        actions.append({
                            "priority": "high",
                            "line": "D",
                            "category": "废渠道",
                            "issue": f"渠道 {ch} CAC过高({info.get('cac', 'inf')})，零转化",
                            "action": f"停用 {ch} 渠道，重新分配预算到高效渠道",
                            "auto_fixable": False,
                        })
                break

    # E线：资金预警
    e = metrics.get("E_line_finance", {})
    if e:
        for report in reports:
            if report["category"] == "analysis" and "finance_e" in report["name"]:
                data = report.get("data", {})
                for alert in data.get("alerts", []):
                    actions.append({
                        "priority": alert.get("severity", "medium"),
                        "line": "E",
                        "category": "成本预警",
                        "issue": alert.get("message", ""),
                        "action": "审查成本结构，优化支出",
                        "auto_fixable": False,
                    })
                for need in data.get("infrastructure_needs", []):
                    if need.get("resource") != "ssl_certificate":  # SSL不需要手动处理
                        actions.append({
                            "priority": "medium",
                            "line": "E",
                            "category": "基础设施扩容",
                            "issue": f"{need.get('resource')}: {need.get('reason', need.get('status', ''))}",
                            "action": f"评估扩容需求: {need.get('suggested', need.get('resource', ''))}",
                            "auto_fixable": False,
                        })
                break

    # F线：运维问题
    f = metrics.get("F_line_ops", {})
    if f:
        for report in reports:
            if report["category"] == "analysis" and "ops_health_f" in report["name"]:
                data = report.get("data", {})
                for ep in data.get("endpoint_checks", []):
                    if ep.get("status") != "ok":
                        actions.append({
                            "priority": "high",
                            "line": "F",
                            "category": "端点异常",
                            "issue": f"{ep['name']} ({ep['url']}) 返回 {ep.get('http_code', '?')}",
                            "action": f"检查并修复 {ep['name']} 端点",
                            "auto_fixable": False,
                        })
                for term in data.get("medical_terms", []):
                    actions.append({
                        "priority": "medium",
                        "line": "F",
                        "category": "医疗用语",
                        "issue": f"文件 {term.get('file', '?')} 包含 '{term.get('term', '?')}'",
                        "action": f"替换 '{term.get('term', '?')}' 为健康管理用语",
                        "auto_fixable": False,
                    })
                break

    # A线：阶段失败
    a = metrics.get("A_line_content", {})
    if a.get("phases_failed", 0) > 0:
        state = load_pipeline_state()
        for phase_name, phase_data in state.get("phases", {}).items():
            if phase_data.get("status") == "failed" or (phase_data.get("error") and phase_data.get("status") == "completed"):
                actions.append({
                    "priority": "medium",
                    "line": "A",
                    "category": "阶段执行异常",
                    "issue": f"阶段 {phase_name} 存在错误: {phase_data.get('error', 'unknown')}",
                    "action": f"检查并修复 {phase_name} 脚本",
                    "auto_fixable": False,
                })

    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return actions


def generate_briefing():
    """生成统一态势简报"""
    state = load_pipeline_state()
    reports = find_latest_reports(days=7)
    metrics = extract_key_metrics(state, reports)
    manual_actions = extract_manual_actions(metrics, reports)

    # 任务执行状态
    task_results = {}
    for task_id, task_info in ALL_TASKS.items():
        phase = task_info.get("phase")
        phase_state = state.get("phases", {}).get(phase, {}) if phase else {}
        task_results[task_id] = {
            "name": task_info["name"],
            "system": task_info["system"],
            "schedule": task_info["schedule"],
            "line": task_info.get("line", "-"),
            "last_status": phase_state.get("status", "not_run"),
            "last_error": phase_state.get("error"),
            "last_run": phase_state.get("completed_at"),
            "output_file": phase_state.get("output_file"),
        }

    briefing = {
        "briefing_id": f"briefing_{datetime.now().strftime('%Y%m%d_%H%M')}",
        "generated_at": datetime.now().isoformat(),
        "pipeline_id": state.get("pipeline_id"),
        "pipeline_status": state.get("status"),
        "summary": {
            "total_tasks": len(ALL_TASKS),
            "tasks_completed": sum(1 for t in task_results.values() if t["last_status"] == "completed"),
            "tasks_failed": sum(1 for t in task_results.values() if t["last_status"] == "failed"),
            "tasks_not_run": sum(1 for t in task_results.values() if t["last_status"] == "not_run"),
            "reports_found": len(reports),
            "manual_actions_count": len(manual_actions),
            "high_priority_count": sum(1 for a in manual_actions if a["priority"] == "high"),
        },
        "task_results": task_results,
        "line_metrics": metrics,
        "manual_actions": manual_actions,
        "recent_reports": [
            {"name": r["name"], "category": r["category"], "modified": r["modified"]}
            for r in reports[:10]
        ],
    }

    return briefing


def save_briefing(briefing):
    """保存简报到文件"""
    output_dir = BASE_DIR / "reports" / "unified_briefing"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{datetime.now().strftime('%Y-%m-%d')}_briefing.json"
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, ensure_ascii=False, indent=2)

    log(f"统一态势简报已保存: {output_path}")
    return output_path


def print_briefing(briefing):
    """打印人类可读的简报"""
    summary = briefing["summary"]
    metrics = briefing["line_metrics"]
    actions = briefing["manual_actions"]

    print("\n" + "=" * 70)
    print(f"  HealthLens 统一态势简报")
    print(f"  生成时间: {briefing['generated_at'][:19]}")
    print(f"  Pipeline: {briefing.get('pipeline_id', '?')} | 状态: {briefing.get('pipeline_status', '?')}")
    print("=" * 70)

    # 任务执行概览
    print(f"\n  [任务执行概览]")
    print(f"    总任务数: {summary['total_tasks']}")
    print(f"    已完成: {summary['tasks_completed']} | 失败: {summary['tasks_failed']} | 未运行: {summary['tasks_not_run']}")
    print(f"    近7天报告: {summary['reports_found']} 份")

    # 六条闭环线指标
    print(f"\n  [六条闭环线指标]")

    a = metrics["A_line_content"]
    print(f"    A线 内容: {a['phases_completed']}/{a['phases_completed']+a['phases_failed']}阶段完成, "
          f"采纳{a['approved_items']}项, 部署{a['deployed_items']}项")

    b = metrics["B_line_conversion"]
    if b:
        print(f"    B线 转化: {b.get('weekly_active_rate', '?')}%周活, "
              f"{b.get('paid_conversion', '?')}%付费, "
              f"流失点{b.get('biggest_dropoff', {}).get('dropoff_rate', '?')}%")

    c = metrics["C_line_data"]
    if c:
        print(f"    C线 数据: {c.get('total_records', '?')}条, "
              f"估值¥{c.get('estimated_value', '?')}, "
              f"新鲜度{c.get('freshness', '?')}")

    d = metrics["D_line_promotion"]
    if d:
        print(f"    D线 推广: {d.get('total_visits', '?')}访问, "
              f"{d.get('total_signups', '?')}注册, "
              f"CAC¥{d.get('overall_cac', '?')}")

    e = metrics["E_line_finance"]
    if e:
        print(f"    E线 资金: 周利润¥{e.get('weekly_profit', '?')}, "
              f"月估¥{e.get('monthly_profit_est', '?')}, "
              f"{e.get('unit_economics', '?')}")

    f = metrics["F_line_ops"]
    if f:
        print(f"    F线 运维: {f.get('overall', '?')}, "
              f"端点{f.get('endpoints_ok', 0)}ok/{f.get('endpoints_error', 0)}err, "
              f"医疗用语{f.get('medical_terms_found', 0)}")

    # 需要手动解决的问题
    if actions:
        print(f"\n  [需要手动解决] ({len(actions)}项, {summary['high_priority_count']}项高优先级)")
        for i, action in enumerate(actions, 1):
            icon = {"high": "[!]", "medium": "[~]", "low": "[ ]"}.get(action["priority"], "[ ]")
            print(f"    {i}. {icon} [{action['line']}线] {action['category']}: {action['issue']}")
            print(f"       -> {action['action']}")
    else:
        print(f"\n  [需要手动解决] 无")

    print("\n" + "=" * 70)


def run():
    """主入口：生成并保存统一态势简报"""
    briefing = generate_briefing()
    save_briefing(briefing)
    print_briefing(briefing)
    return briefing


if __name__ == "__main__":
    run()
