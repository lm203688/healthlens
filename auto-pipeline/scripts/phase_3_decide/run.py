"""
阶段3：决策门禁
基于分析结果做出最终决策，生成开发队列
输出：decision_report.json + 更新 approved_queue
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import (
    BASE_DIR,
    complete_phase,
    fail_phase,
    get_phase_output,
    get_state,
    log,
    save_state,
    start_phase,
)


def deduplicate_approved_items(approved_items, historical_items):
    """去重：检查是否与历史批准项重复"""
    new_items = []
    for item in approved_items:
        is_duplicate = False
        for hist in historical_items:
            if item.get("id") == hist.get("id"):
                is_duplicate = True
                break
            # 标题相似度检查（简化版）
            if item.get("title") and hist.get("title"):
                if item["title"][:20] == hist["title"][:20]:
                    is_duplicate = True
                    break
        if not is_duplicate:
            new_items.append(item)
    return new_items


def prioritize_items(approved_items, config):
    """对批准项进行优先级排序"""
    def priority_score(item):
        score = item.get("total_score", 0)
        # 高相关性额外加权
        if item.get("relevance_to_healthlens") == "high":
            score += 10
        # 高可行性优先
        if item.get("technical_feasibility", 0) >= 0.8:
            score += 5
        # 市场验证强优先
        signals = item.get("market_signals", {})
        if len([v for v in signals.values() if v]) >= 3:
            score += 5
        return score

    return sorted(approved_items, key=priority_score, reverse=True)


def assign_content_tasks(prioritized_items, config):
    """为每个批准项分配具体的内容/开发任务"""
    targets = config["content_targets"]
    max_seo = targets["seo_knowledge_pages"]["max_per_week"]
    max_edu = targets["user_education"]["max_per_week"]

    tasks = []
    seo_count = 0
    edu_count = 0

    for item in prioritized_items:
        content_types = item.get("recommendation", {}).get("content_types", [])

        for ct in content_types:
            if "知识文章" in ct or "趋势分析" in ct or "知识库" in ct:
                if seo_count < max_seo:
                    tasks.append({
                        "task_id": f"task_seo_{len(tasks)+1:03d}",
                        "type": "seo_knowledge_page",
                        "based_on_item": item["id"],
                        "title": item["title"],
                        "priority": item.get("recommendation", {}).get("priority", "medium"),
                        "status": "queued",
                        "tags": item.get("tags", []),
                        "target_word_count": 2000
                    })
                    seo_count += 1
                    break

            if "用户教育" in ct:
                if edu_count < max_edu:
                    tasks.append({
                        "task_id": f"task_edu_{len(tasks)+1:03d}",
                        "type": "user_education",
                        "based_on_item": item["id"],
                        "title": item["title"],
                        "priority": "medium",
                        "status": "queued",
                        "tags": item.get("tags", []),
                        "target_word_count": 1200
                    })
                    edu_count += 1
                    break

    return tasks


def run():
    phase = "decide"
    try:
        start_phase(phase)

        # 读取配置
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            config = json.load(f)

        # 读取分析阶段输出
        analysis_data = get_phase_output("analyze")
        if not analysis_data:
            fail_phase(phase, "无法读取分析阶段输出")
            return False

        # 获取当前状态中的历史批准项
        state = get_state()
        historical_approved = state.get("approved_queue", [])

        # 1. 去重
        approved = analysis_data.get("approved_items", [])
        new_approved = deduplicate_approved_items(approved, historical_approved)

        # 2. 优先级排序
        prioritized = prioritize_items(new_approved, config)

        # 3. 分配开发/内容任务
        tasks = assign_content_tasks(prioritized, config)

        # 4. 更新队列
        watch_items = analysis_data.get("watch_items", [])
        rejected_items = analysis_data.get("rejected_items", [])

        # 合并到全局状态
        state["approved_queue"] = historical_approved + prioritized
        state["watch_queue"] = state.get("watch_queue", []) + [
            {"item": w, "added_at": datetime.now().isoformat(), "next_review": "2weeks"}
            for w in watch_items
        ]
        state["rejected_items"] = state.get("rejected_items", []) + [
            {"item": r, "rejected_at": datetime.now().isoformat()}
            for r in rejected_items
        ]
        state["development_tasks"] = tasks
        state["status"] = "ready_develop"

        save_state(state)

        # 生成决策报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"decision_{today}",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "new_approved": len(new_approved),
                "total_approved": len(state["approved_queue"]),
                "watch_count": len(state["watch_queue"]),
                "rejected_count": len(state["rejected_items"]),
                "tasks_created": len(tasks)
            },
            "high_priority_tasks": [t for t in tasks if t["priority"] == "high"],
            "all_tasks": tasks,
            "decisions": [
                {
                    "item_id": item["id"],
                    "title": item["title"],
                    "score": item["total_score"],
                    "decision": "approved",
                    "rationale": f"综合评分 {item['total_score']} ≥ {config['decision_gate']['approved_threshold']}",
                    "assigned_tasks": [t["task_id"] for t in tasks if t["based_on_item"] == item["id"]]
                }
                for item in prioritized
            ] + [
                {
                    "item_id": item["id"],
                    "title": item["title"],
                    "score": item["total_score"],
                    "decision": "watch",
                    "rationale": f"评分 {item['total_score']} 介于观察区间"
                }
                for item in watch_items
            ] + [
                {
                    "item_id": item["id"],
                    "title": item["title"],
                    "score": item["total_score"],
                    "decision": "reject",
                    "rationale": f"评分 {item['total_score']} 低于阈值"
                }
                for item in rejected_items
            ]
        }

        # 保存报告
        output_file = f"reports/analysis/{today}_decision_report.json"
        output_path = BASE_DIR / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(approved) + len(watch_items) + len(rejected_items),
            tasks_created=len(tasks),
            new_approved=len(new_approved)
        )
        log(f"决策门禁完成: {len(new_approved)} 项新批准, {len(tasks)} 个任务")
        return True

    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
