"""
HealthLens 统一定时任务注册表
归集 Celery Beat + auto-pipeline 两套系统的所有定时任务

所有定时任务的唯一真实来源（Single Source of Truth）
任何新增定时任务必须在此注册
"""
from datetime import datetime
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent

# ===== A线：auto-pipeline 闭环工作流（6阶段 + 6反馈） =====
PIPELINE_A_TASKS = {
    "pipeline-a-collect": {
        "name": "A线·情报收集",
        "system": "auto-pipeline",
        "script": "scripts/phase_1_collect/run.py",
        "schedule": "每周一 03:00",
        "cron": "0 3 * * 1",
        "line": "A",
        "phase": "collect",
        "description": "从GitHub/arXiv/HuggingFace/竞品等渠道收集健康领域情报",
        "output_dir": "reports/intelligence",
    },
    "pipeline-a-analyze": {
        "name": "A线·智能分析",
        "system": "auto-pipeline",
        "script": "scripts/phase_2_analyze/run.py",
        "schedule": "每周一 03:05",
        "cron": "5 3 * * 1",
        "line": "A",
        "phase": "analyze",
        "description": "对收集的情报进行评分、分类、提取可操作洞察",
        "output_dir": "reports/analysis",
    },
    "pipeline-a-decide": {
        "name": "A线·决策门禁",
        "system": "auto-pipeline",
        "script": "scripts/phase_3_decide/run.py",
        "schedule": "每周一 03:10",
        "cron": "10 3 * * 1",
        "line": "A",
        "phase": "decide",
        "description": "基于核心目标符合性门禁决定采纳/观察/拒绝",
        "output_dir": "reports/analysis",
    },
    "pipeline-a-develop": {
        "name": "A线·内容开发",
        "system": "auto-pipeline",
        "script": "scripts/phase_4_develop/run.py",
        "schedule": "每周一 03:15",
        "cron": "15 3 * * 1",
        "line": "A",
        "phase": "develop",
        "description": "将采纳的情报开发为SEO知识页面和用户教育内容",
        "output_dir": "reports/analysis",
    },
    "pipeline-a-test": {
        "name": "A线·质量测试",
        "system": "auto-pipeline",
        "script": "scripts/phase_5_test/run.py",
        "schedule": "每周一 03:20",
        "cron": "20 3 * * 1",
        "line": "A",
        "phase": "test",
        "description": "医疗用语扫描、Schema标记验证、SEO关键词检查",
        "output_dir": "reports/analysis",
    },
    "pipeline-a-deploy": {
        "name": "A线·部署上架",
        "system": "auto-pipeline",
        "script": "scripts/phase_6_deploy/run.py",
        "schedule": "每周一 03:25",
        "cron": "25 3 * * 1",
        "line": "A",
        "phase": "deploy",
        "description": "将通过测试的内容部署到生产服务器并更新sitemap",
        "output_dir": "reports/deployed",
    },
}

# ===== B~F线：反馈闭环 =====
FEEDBACK_TASKS = {
    "feedback-a": {
        "name": "A线·效果追踪反馈",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/feedback_a.py",
        "schedule": "每周一 03:30",
        "cron": "30 3 * * 1",
        "line": "A",
        "phase": "feedback_a",
        "description": "追踪已部署内容的CTR、转化率，反馈调整决策权重",
        "output_dir": "reports/analysis",
    },
    "feedback-b": {
        "name": "B线·用户转化闭环",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/user_conversion_b.py",
        "schedule": "每周一 03:35",
        "cron": "35 3 * * 1",
        "line": "B",
        "phase": "user_conversion_b",
        "description": "分析用户漏斗、留存率、付费转化，识别流失点",
        "output_dir": "reports/analysis",
    },
    "feedback-c": {
        "name": "C线·数据资产闭环",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/data_asset_c.py",
        "schedule": "每周一 03:40",
        "cron": "40 3 * * 1",
        "line": "C",
        "phase": "data_asset_c",
        "description": "检查数据库新鲜度、完整性，触发增量同步",
        "output_dir": "reports/analysis",
    },
    "feedback-d": {
        "name": "D线·推广营销闭环",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/promotion_d.py",
        "schedule": "每周一 03:45",
        "cron": "45 3 * * 1",
        "line": "D",
        "phase": "promotion_d",
        "description": "分析推广渠道ROI、CAC，优化预算分配",
        "output_dir": "reports/analysis",
    },
    "feedback-e": {
        "name": "E线·资金闭环",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/finance_e.py",
        "schedule": "每周一 03:50",
        "cron": "50 3 * * 1",
        "line": "E",
        "phase": "finance_e",
        "description": "核算收支、单位经济效益、成本预警、扩容提醒",
        "output_dir": "reports/analysis",
    },
    "feedback-f": {
        "name": "F线·项目运维闭环",
        "system": "auto-pipeline",
        "script": "scripts/phase_7_feedback/ops_health_f.py",
        "schedule": "每周一 03:55",
        "cron": "55 3 * * 1",
        "line": "F",
        "phase": "ops_health_f",
        "description": "服务器健康、安全、CI/CD、医疗用语扫描",
        "output_dir": "reports/analysis",
    },
}

# ===== Celery Beat 定时任务（运行在服务器Docker内） =====
CELERY_TASKS = {
    "seo-generate-conditions": {
        "name": "SEO知识页面生成-病症类",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.seo_batch_generate",
        "schedule": "每周三 03:00",
        "cron": "0 3 * * 3",
        "args": [10, "conditions"],
        "description": "批量生成10篇病症类SEO知识页面",
        "output": "写入数据库 seo_pages 表",
    },
    "seo-generate-herbs": {
        "name": "SEO知识页面生成-本草类",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.seo_batch_generate",
        "schedule": "每周六 03:00",
        "cron": "0 3 * * 6",
        "args": [10, "herbs"],
        "description": "批量生成10篇本草类SEO知识页面",
        "output": "写入数据库 seo_pages 表",
    },
    "seo-auto-publish": {
        "name": "SEO自动审核发布",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.seo_auto_publish",
        "schedule": "每日 04:00",
        "cron": "0 4 * * *",
        "args": [10],
        "description": "审核待发布SEO页面并自动上线",
        "output": "更新 seo_pages 状态为 published",
    },
    "user-education-push": {
        "name": "用户教育内容推送",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.user_education_push",
        "schedule": "每周五 03:00",
        "cron": "0 3 * * 5",
        "args": [],
        "description": "生成并推送用户教育内容（短视频脚本/图文卡片/数据海报）",
        "output": "写入 notifications 表",
    },
    "cleanup-expired-invites": {
        "name": "过期邀请码清理",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.cleanup_expired_invites",
        "schedule": "每日 05:00",
        "cron": "0 5 * * *",
        "args": [],
        "description": "清理过期的邀请码和推荐记录",
        "output": "删除过期记录",
    },
    "cleanup-old-analytics": {
        "name": "过期分析数据清理",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.cleanup_old_analytics",
        "schedule": "每周日 05:00",
        "cron": "0 5 * * 0",
        "args": [90],
        "description": "清理90天前的分析数据",
        "output": "删除过期分析记录",
    },
    "reactivate-silent-users": {
        "name": "沉默用户唤醒(3天)",
        "system": "celery",
        "task": "app.tasks.engagement_tasks.reactivate_silent_users",
        "schedule": "每日 06:00",
        "cron": "0 6 * * *",
        "args": [3],
        "description": "对3天未活跃用户发送温和提醒",
        "output": "写入 notifications 表",
    },
    "reactivate-deep-silent": {
        "name": "深度沉默用户唤醒(7天)",
        "system": "celery",
        "task": "app.tasks.engagement_tasks.reactivate_silent_users",
        "schedule": "每周二 06:00",
        "cron": "0 6 * * 2",
        "args": [7],
        "description": "对7天未活跃用户发送中度提醒",
        "output": "写入 notifications 表",
    },
    "acquisition-weekly-report": {
        "name": "获客数据周报",
        "system": "celery",
        "task": "app.tasks.acquisition_tasks.acquisition_weekly_report",
        "schedule": "每周一 05:00",
        "cron": "0 5 * * 1",
        "args": [],
        "description": "生成获客渠道数据周报",
        "output": "写入数据库 analytics 表",
    },
}

# ===== 周期性报告任务（通过Schedule工具调度） =====
REPORT_TASKS = {
    "monthly-comprehensive-report": {
        "name": "月度综合报告",
        "system": "schedule",
        "schedule": "每月1日 03:00",
        "cron": "0 3 1 * *",
        "description": "汇总月度Agent研判、推广技术、数据资产、资金核算、服务器成本、Freemium收入",
        "output_dir": "reports/monthly",
    },
    "quarterly-strategy-report": {
        "name": "季度策略报告",
        "system": "schedule",
        "schedule": "每季首月1日 04:00",
        "cron": "0 4 1 1,4,7,10 *",
        "description": "三原则审查、竞品格局、下季度路线图、基础设施审查",
        "output_dir": "reports/quarterly",
    },
    "promotion-tech-tracking": {
        "name": "推广技术深度追踪",
        "system": "schedule",
        "schedule": "每月15日 03:00",
        "cron": "0 3 15 * *",
        "description": "Google算法更新、GrowthHackers/IndieHackers/ProductHunt、工具更新追踪",
        "output_dir": "reports/promotion",
    },
}

# ===== 统一任务清单 =====
ALL_TASKS = {**PIPELINE_A_TASKS, **FEEDBACK_TASKS, **CELERY_TASKS, **REPORT_TASKS}


def get_all_tasks():
    """获取所有注册的定时任务"""
    return ALL_TASKS


def get_tasks_by_system(system):
    """按系统获取任务"""
    return {k: v for k, v in ALL_TASKS.items() if v["system"] == system}


def get_tasks_by_line(line):
    """按闭环线获取任务"""
    return {k: v for k, v in ALL_TASKS.items() if v.get("line") == line}


def get_task_schedule_summary():
    """获取任务调度时间表摘要（按时间排序）"""
    schedule_list = []
    for task_id, task in ALL_TASKS.items():
        schedule_list.append({
            "task_id": task_id,
            "name": task["name"],
            "system": task["system"],
            "schedule": task["schedule"],
            "cron": task.get("cron", ""),
            "line": task.get("line", "-"),
            "description": task["description"],
        })
    return schedule_list


def print_registry():
    """打印任务注册表"""
    tasks = get_task_schedule_summary()
    print("\n" + "=" * 80)
    print("  HealthLens 统一定时任务注册表")
    print(f"  总计: {len(tasks)} 个定时任务")
    print("=" * 80)

    # 按系统分组
    for system in ["auto-pipeline", "celery", "schedule"]:
        sys_tasks = [t for t in tasks if t["system"] == system]
        if not sys_tasks:
            continue
        print(f"\n  [{system.upper()}] ({len(sys_tasks)}个)")
        for t in sys_tasks:
            print(f"    {t['schedule']:20s} | {t['name']:30s} | 线{t['line']} | {t['description'][:40]}")

    print("\n" + "=" * 80)
    return tasks


if __name__ == "__main__":
    print_registry()
