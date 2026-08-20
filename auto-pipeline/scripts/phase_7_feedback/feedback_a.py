"""
A线补齐：效果追踪反馈
从部署后的页面收集SEO数据（搜索排名、流量、索引状态），回写到pipeline_state
校准决策权重：根据实际效果调整来源/市场/可行性评分权重
输出：feedback_report.json + 更新config.json中的权重
"""
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import get_state, save_state, BASE_DIR, log, start_phase, complete_phase, fail_phase


def try_google_search_console(deployed_items):
    """尝试从 Google Search Console API 获取真实 SEO 数据
    
    需要配置：
    1. Google Cloud 服务账号 JSON 密钥
    2. siteUrl = sc-domain:healthlens.cc
    
    如果未配置，返回 None 降级到占位数据。
    """
    import os
    credentials_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not credentials_path or not Path(credentials_path).exists():
        return None
    
    try:
        import urllib.request
        import urllib.error
        
        # 使用 Service Account 进行 OAuth2 获取 access_token
        # 这里简化实现：直接返回 None 让调用方降级
        # 完整实现需要 google-auth 库
        return None
    except Exception:
        return None


def collect_seo_feedback(deployed_items):
    """收集 SEO 效果数据（真实 API 或安全降级）"""
    # 尝试真实 API
    real_data = try_google_search_console(deployed_items)
    if real_data:
        return real_data, "google_search_console"
    
    # 降级：返回占位数据（标记为 placeholder，不伪造指标）
    feedback = []
    for item in deployed_items:
        slug = Path(item.get("content_file", "")).stem if item.get("content_file") else "unknown"
        feedback.append({
            "slug": slug,
            "title": item.get("title", ""),
            "deployed_days": 0,
            "metrics": {
                "google_indexed": None,
                "impressions": None,
                "clicks": None,
                "avg_position": None,
                "ctr": None,
            },
            "performance": "unknown",
            "data_source": "placeholder",
        })
    return feedback, "placeholder"


def calculate_weight_adjustments(feedback, current_weights):
    """根据效果反馈计算权重调整建议"""
    above_count = sum(1 for f in feedback if f["performance"] == "above_average")
    total = len(feedback) if feedback else 1
    success_rate = above_count / total
    
    adjustments = {}
    
    # 如果成功率低，增加市场验证和可行性的权重
    if success_rate < 0.5:
        adjustments["market_validation"] = {"current": current_weights.get("market_validation", 20), "suggested": 25, "reason": "内容表现不佳，需加强市场验证筛选"}
        adjustments["feasibility"] = {"current": current_weights.get("feasibility", 10), "suggested": 15, "reason": "技术可行性评估需更严格"}
        adjustments["source_count"] = {"current": current_weights.get("source_count", 40), "suggested": 35, "reason": "降低来源数量权重，避免伪信号"}
    elif success_rate >= 0.8:
        adjustments["source_count"] = {"current": current_weights.get("source_count", 40), "suggested": 45, "reason": "内容表现优秀，可适当放宽筛选标准增加产出"}
    
    return adjustments, success_rate


def run():
    phase = "feedback_a"
    try:
        start_phase(phase)
        
        state = get_state()
        deployed = [t for t in state.get("development_tasks", []) if t.get("status") == "deployed"]
        
        if not deployed:
            log("A线反馈：无已部署内容，跳过")
            complete_phase(phase, items_processed=0)
            return True
        
        # 收集效果数据（真实 API 或占位）
        feedback, data_source = collect_seo_feedback(deployed)
        
        # 计算权重调整（仅在有真实数据时调整）
        config_path = BASE_DIR / "config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        current_weights = config["decision_gate"]["weights"]
        
        adjustments = {}
        success_rate = 0
        if data_source != "placeholder" and feedback:
            above_count = sum(1 for f in feedback if f.get("performance") == "above_average")
            total = len(feedback)
            success_rate = above_count / total if total else 0
            adjustments, success_rate = calculate_weight_adjustments(feedback, current_weights)
        
        # 更新反馈指标到状态
        state.setdefault("feedback_metrics", {})["content_pipeline"] = {
            "checked_at": datetime.now().isoformat(),
            "data_source": data_source,
            "total_deployed": len(deployed),
            "success_rate": round(success_rate * 100, 1) if data_source != "placeholder" else None,
            "top_performer": None if data_source == "placeholder" else (max(feedback, key=lambda x: x.get("metrics", {}).get("clicks") or 0)["slug"] if feedback else None),
            "weight_adjustments": adjustments
        }
        
        # 如果有调整建议且数据来源真实，应用到配置
        if adjustments and data_source != "placeholder":
            for key, adj in adjustments.items():
                config["decision_gate"]["weights"][key] = adj["suggested"]
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            log(f"决策权重已调整: {list(adjustments.keys())}")
        
        save_state(state)
        
        report = {
            "report_id": f"feedback_a_{datetime.now().strftime('%Y%m%d')}",
            "generated_at": datetime.now().isoformat(),
            "data_source": data_source,
            "success_rate": round(success_rate * 100, 1) if data_source != "placeholder" else None,
            "feedback_count": len(feedback),
            "adjustments_made": len(adjustments) > 0 and data_source != "placeholder",
            "adjustments": adjustments,
            "feedback_details": feedback
        }
        
        output_file = f"reports/analysis/{datetime.now().strftime('%Y-%m-%d')}_feedback_a.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        complete_phase(phase, output_file=output_file, items_processed=len(feedback))
        log(f"A线反馈完成 (数据源={data_source}): 成功率 {success_rate*100:.0f}%, 权重调整 {len(adjustments)} 项")
        return True
    except Exception as e:
        fail_phase(phase, str(e))
        return False


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
