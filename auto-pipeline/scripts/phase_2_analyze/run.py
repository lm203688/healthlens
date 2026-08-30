"""
阶段2：智能分析
对收集到的情报进行分析和评分，识别高价值项目
输出：analysis_report.json（包含评分和分类）
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
    log,
    start_phase,
)


def calculate_score(item, config):
    """计算单个情报项的综合评分"""
    weights = config["decision_gate"]["weights"]
    score = 0
    details = {}

    # 1. 来源数量评分（最多40分）
    source_count = len(item.get("sources", []))
    source_score = min(source_count * (weights["source_count"] / 3), weights["source_count"])
    # 来源多样性加分
    source_types = set(s.get("type", "") for s in item.get("sources", []))
    if len(source_types) >= 2:
        source_score += 5  # 多类型来源额外加分
    source_score = min(source_score, weights["source_count"])
    details["source_score"] = round(source_score, 1)
    details["source_count"] = source_count
    details["source_types"] = len(source_types)
    score += source_score

    # 2. 核心目标符合度（最多30分）
    relevance = item.get("relevance_to_healthlens", "low")
    relevance_map = {"high": 1.0, "medium": 0.6, "low": 0.3}
    goal_score = weights["goal_alignment"] * relevance_map.get(relevance, 0.3)
    details["goal_score"] = round(goal_score, 1)
    details["relevance"] = relevance
    score += goal_score

    # 3. 市场验证信号（最多20分）
    market_signals = item.get("market_signals", {})
    market_score = 0
    signal_count = sum(1 for v in market_signals.values() if v and v != "N/A")
    if signal_count >= 3:
        market_score = weights["market_validation"]
    elif signal_count >= 2:
        market_score = weights["market_validation"] * 0.7
    elif signal_count >= 1:
        market_score = weights["market_validation"] * 0.4
    details["market_score"] = round(market_score, 1)
    details["signal_count"] = signal_count
    score += market_score

    # 4. 技术可行性（最多10分）
    feasibility = item.get("technical_feasibility", 0.5)
    feas_score = weights["feasibility"] * feasibility
    details["feasibility_score"] = round(feas_score, 1)
    details["feasibility"] = feasibility
    score += feas_score

    return round(score, 1), details


def classify_item(score, config):
    """根据评分分类"""
    thresholds = config["decision_gate"]
    if score >= thresholds["approved_threshold"]:
        return "approved"
    elif score >= thresholds["watch_threshold"]:
        return "watch"
    else:
        return "reject"


def generate_recommendation(item, category):
    """生成具体行动建议"""
    if category == "approved":
        insights = item.get("actionable_insight", "")
        return {
            "action": "develop_content",
            "priority": "high" if item.get("relevance_to_healthlens") == "high" else "medium",
            "content_types": _suggest_content_types(item),
            "rationale": insights
        }
    elif category == "watch":
        return {
            "action": "monitor",
            "review_interval": "2weeks",
            "key_indicators": ["市场接受度", "技术成熟度", "竞品动态"]
        }
    else:
        return {
            "action": "archive",
            "reason": "当前价值不高，建议后续重新评估"
        }


def _suggest_content_types(item):
    """根据情报项类型建议内容形式"""
    category = item.get("category", "")
    tags = item.get("tags", [])
    types = []

    if category == "academic":
        types.append("深度知识文章")
        types.append("科研速递")
    elif category == "tech_trend":
        types.append("趋势分析文章")
        types.append("知识库更新")
    elif category == "market":
        types.append("行业洞察")
        types.append("用户教育内容")

    if "睡眠" in str(tags) or "sleep" in str(tags).lower():
        types.append("睡眠修复专题")
    if "营养" in str(tags) or "diet" in str(tags).lower():
        types.append("营养指南")

    return types[:3]


def run():
    phase = "analyze"
    try:
        start_phase(phase)

        # 读取配置
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            config = json.load(f)

        # 读取收集阶段的输出
        intel_data = get_phase_output("collect")
        if not intel_data:
            fail_phase(phase, "无法读取收集阶段输出")
            return False

        # 分析每个情报项
        analyzed_items = []
        for item in intel_data.get("items", []):
            score, details = calculate_score(item, config)
            category = classify_item(score, config)
            recommendation = generate_recommendation(item, category)

            analyzed_items.append({
                **item,
                "total_score": score,
                "score_breakdown": details,
                "category": category,
                "recommendation": recommendation
            })

        # 按分数排序
        analyzed_items.sort(key=lambda x: x["total_score"], reverse=True)

        # 分类统计
        approved = [i for i in analyzed_items if i["category"] == "approved"]
        watch = [i for i in analyzed_items if i["category"] == "watch"]
        rejected = [i for i in analyzed_items if i["category"] == "reject"]

        # 生成分析报告
        today = datetime.now().strftime("%Y-%m-%d")
        report = {
            "report_id": f"analysis_{today}",
            "generated_at": datetime.now().isoformat(),
            "total_items": len(analyzed_items),
            "summary": {
                "approved": len(approved),
                "watch": len(watch),
                "reject": len(rejected)
            },
            "top_scorers": [
                {"id": i["id"], "title": i["title"], "score": i["total_score"], "category": i["category"]}
                for i in approved[:5]
            ],
            "approved_items": approved,
            "watch_items": watch,
            "rejected_items": rejected,
            "content_pipeline": {
                "knowledge_articles": [i for i in approved if "深度知识文章" in i["recommendation"].get("content_types", [])],
                "trend_analysis": [i for i in approved if "趋势分析文章" in i["recommendation"].get("content_types", [])],
                "user_education": [i for i in approved if "用户教育内容" in i["recommendation"].get("content_types", [])]
            },
            "key_insights": [
                f"本周共分析 {len(analyzed_items)} 条情报",
                f"其中 {len(approved)} 条通过决策门禁，建议立即推进",
                f"{len(watch)} 条进入观察列表，持续跟踪",
                f"高优先级项目: {', '.join(i['title'][:20] for i in approved[:3])}"
            ]
        }

        # 保存报告
        output_file = f"reports/analysis/{today}_analysis_report.json"
        output_path = BASE_DIR / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(
            phase,
            output_file=output_file,
            items_processed=len(analyzed_items),
            approved_count=len(approved),
            watch_count=len(watch),
            rejected_count=len(rejected)
        )
        log(f"分析完成: {len(approved)} 通过, {len(watch)} 观察, {len(rejected)} 放弃")
        return True

    except Exception as e:
        import traceback
        fail_phase(phase, f"{str(e)}\n{traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
