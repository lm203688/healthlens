"""
A线补齐：效果追踪反馈
从部署后的页面收集SEO数据（HTTP存活、响应速度、内容完整性），回写到pipeline_state
校准决策权重：根据实际效果调整来源/市场/可行性评分权重
输出：feedback_report.json + 更新config.json中的权重

注意：Google Search Console 在国内无法访问，已移除。
改用HTTP存活探测 + 内容完整性检查作为效果追踪数据源。
"""
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import get_state, save_state, BASE_DIR, log, start_phase, complete_phase, fail_phase


def probe_page_health(url, timeout=10):
    """探测单个页面的健康状态（HTTP状态码、响应时间、内容大小）"""
    try:
        start = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "HealthLens-FeedbackProbe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            body = resp.read(50000)
            latency_ms = int((time.time() - start) * 1000)
            return {
                "http_code": code,
                "latency_ms": latency_ms,
                "body_size": len(body),
                "status": "ok" if 200 <= code < 400 else "error",
            }
    except urllib.error.HTTPError as e:
        return {"http_code": e.code, "latency_ms": 0, "body_size": 0, "status": "error"}
    except Exception as e:
        return {"http_code": 0, "latency_ms": 0, "body_size": 0, "status": "error", "error": str(e)[:100]}


def collect_seo_feedback(deployed_items):
    """收集页面健康数据（HTTP探测，无需外部平台依赖）"""
    project_url = "https://healthlens.cc"
    feedback = []

    # 探测核心页面
    core_pages = [
        f"{project_url}/",
        f"{project_url}/robots.txt",
        f"{project_url}/sitemap.xml",
        f"{project_url}/llms.txt",
    ]
    core_results = [probe_page_health(url) for url in core_pages]
    core_ok = sum(1 for r in core_results if r["status"] == "ok")
    core_total = len(core_results)
    core_avg_latency = sum(r["latency_ms"] for r in core_results) / max(core_total, 1)

    for item in deployed_items:
        slug = Path(item.get("content_file", "")).stem if item.get("content_file") else "unknown"
        url = f"{project_url}/{slug}.html"
        probe = probe_page_health(url)

        # 根据探测结果判定表现
        if probe["status"] == "ok" and probe["latency_ms"] < 2000:
            performance = "above_average"
        elif probe["status"] == "ok":
            performance = "average"
        else:
            performance = "below_average"

        feedback.append({
            "slug": slug,
            "title": item.get("title", ""),
            "deployed_days": 0,
            "metrics": {
                "http_code": probe["http_code"],
                "latency_ms": probe["latency_ms"],
                "body_size": probe["body_size"],
            },
            "performance": performance,
            "data_source": "http_probe",
        })

    # 汇总核心页面健康度
    feedback.insert(0, {
        "slug": "__core_health__",
        "title": "核心页面健康度",
        "deployed_days": 0,
        "metrics": {
            "core_pages_ok": core_ok,
            "core_pages_total": core_total,
            "avg_latency_ms": round(core_avg_latency),
        },
        "performance": "above_average" if core_ok == core_total else ("average" if core_ok > 0 else "below_average"),
        "data_source": "http_probe",
    })

    return feedback, "http_probe"


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
        
        # 收集效果数据（HTTP探测，真实数据）
        feedback, data_source = collect_seo_feedback(deployed)
        
        # 计算权重调整（有真实HTTP探测数据时调整）
        config_path = BASE_DIR / "config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        current_weights = config["decision_gate"]["weights"]
        
        adjustments = {}
        success_rate = 0
        if feedback:
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
            "top_performer": None if data_source != "http_probe" else (max(feedback, key=lambda x: x.get("metrics", {}).get("latency_ms") or 9999)["slug"] if feedback else None),
            "weight_adjustments": adjustments
        }
        
        # 如果有调整建议且数据来源真实，应用到配置
        if adjustments and data_source == "http_probe":
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
