"""
D线：推广营销闭环
追踪5个渠道（SEO/社交/裂变/唤醒/品牌）的效果
计算ROI、转化归因、淘汰低效渠道
输出：promotion_report.json + 更新渠道权重

注意：各渠道数据当前为占位数据（placeholder），需要接入真实数据源：
- SEO：可通过HTTP探测获取页面健康度（已在feedback_a中实现），流量数据需接入百度统计
- Social：各平台开放平台API
- Referral：数据库 referral_events 表
- Brand：社交媒体监控API
"""
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import get_state, save_state, BASE_DIR, log, start_phase, complete_phase, fail_phase


def _probe_seo_health():
    """通过HTTP探测获取SEO渠道基础数据（真实数据，无需外部平台）"""
    project_url = "https://healthlens.cc"
    pages = ["/", "/robots.txt", "/sitemap.xml", "/llms.txt"]
    ok_count = 0
    total = len(pages)
    for path in pages:
        try:
            req = urllib.request.Request(project_url + path, headers={"User-Agent": "HealthLens-PromoCheck/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 400:
                    ok_count += 1
        except Exception:
            pass
    return {
        "pages_healthy": ok_count,
        "pages_total": total,
        "health_rate": round(ok_count / max(total, 1) * 100, 1),
    }


def get_channel_metrics():
    """获取各推广渠道数据
    
    SEO渠道：通过HTTP探测获取页面健康度（真实数据）
    其他渠道：当前为占位数据，需接入真实数据源
    """
    seo_health = _probe_seo_health()
    
    return {
        "SEO": {
            "visits": 0, "signups": 0, "conversions": 0, "cost": 0,
            "content_pages": seo_health["pages_total"],
            "pages_healthy": seo_health["pages_healthy"],
            "health_rate": seo_health["health_rate"],
            "data_source": "http_probe",
            "note": f"页面健康度 {seo_health['health_rate']}%，流量数据需接入百度统计"
        },
        "social": {"visits": 0, "signups": 0, "conversions": 0, "cost": 0, "posts": 0, "data_source": "placeholder"},
        "referral": {"visits": 0, "signups": 0, "conversions": 0, "cost": 0, "invites_sent": 0, "data_source": "placeholder"},
        "wake_up": {"visits": 0, "signups": 0, "conversions": 0, "cost": 0, "status": "discontinued", "discontinued_reason": "零转化，CAC无穷大", "data_source": "placeholder"},
        "brand": {"visits": 0, "signups": 0, "conversions": 0, "cost": 0, "mentions": 0, "data_source": "placeholder"},
    }


def calculate_roi(channels):
    """计算各渠道ROI"""
    results = {}
    for name, data in channels.items():
        if data.get("status") == "discontinued":
            results[name] = {
                "visits": 0, "signups": 0, "cost": 0,
                "signup_rate": 0, "cac": 0,
                "efficiency": "discontinued",
                "trend": "discontinued",
                "note": data.get("discontinued_reason", "已停用"),
                "data_source": data.get("data_source", "unknown"),
            }
            continue

        visits = data["visits"]
        signups = data["signups"]
        cost = data["cost"]
        signup_rate = round(signups / max(visits, 1) * 100, 1)
        cac = round(cost / max(signups, 1), 2) if signups > 0 else float("inf")
        
        if cost == 0:
            efficiency = "free_high" if signup_rate > 2 else "free_low"
        else:
            efficiency = "paid_good" if cac < 50 else "paid_poor"
        
        results[name] = {
            "visits": visits, "signups": signups, "cost": cost,
            "signup_rate": signup_rate, "cac": cac,
            "efficiency": efficiency,
            "trend": "stable",
            "data_source": data.get("data_source", "unknown"),
        }
    return results


def evaluate_channels(roi_results):
    """评估渠道并给出调整建议"""
    actions = []
    for name, data in roi_results.items():
        if data["efficiency"] == "discontinued":
            actions.append({"channel": name, "action": "discontinued", "reason": data.get("note", "已停用"), "priority": "low"})
        elif data["efficiency"] == "paid_poor":
            actions.append({"channel": name, "action": "reduce_budget", "reason": f"CAC过高(¥{data['cac']})", "priority": "high"})
        elif data["efficiency"] == "free_high":
            actions.append({"channel": name, "action": "increase_effort", "reason": f"零成本高效(signup_rate {data['signup_rate']}%)", "priority": "medium"})
        elif data["efficiency"] == "free_low":
            actions.append({"channel": name, "action": "optimize_content", "reason": f"零成本但转化率低({data['signup_rate']}%)", "priority": "low"})
        elif data["efficiency"] == "paid_good":
            actions.append({"channel": name, "action": "maintain", "reason": f"付费效率可接受(CAC ¥{data['cac']})", "priority": "medium"})
    return actions


def run():
    phase = "promotion_d"
    try:
        start_phase(phase)
        
        channels = get_channel_metrics()
        roi = calculate_roi(channels)
        actions = evaluate_channels(roi)
        
        total_visits = sum(c["visits"] for c in channels.values())
        total_signups = sum(c["signups"] for c in channels.values())
        total_cost = sum(c["cost"] for c in channels.values())
        overall_cac = round(total_cost / max(total_signups, 1), 2)
        
        state = get_state()
        state.setdefault("feedback_metrics", {})["promotion"] = {
            "checked_at": datetime.now().isoformat(),
            "data_source": "mixed",
            "seo_data_source": "http_probe",
            "total_visits": total_visits,
            "total_signups": total_signups,
            "overall_cac": overall_cac,
            "channel_actions": len([a for a in actions if a["action"] in ["reduce_budget", "increase_effort"]])
        }
        save_state(state)
        
        report = {
            "report_id": f"promotion_d_{datetime.now().strftime('%Y%m%d')}",
            "generated_at": datetime.now().isoformat(),
            "data_source": "mixed",
            "total_visits": total_visits,
            "total_signups": total_signups,
            "total_cost": total_cost,
            "overall_cac": overall_cac,
            "channel_roi": roi,
            "actions": actions,
            "recommendations": [
                {"priority": "high", "action": a["action"], "channel": a["channel"], "reason": a["reason"]}
                for a in actions if a["priority"] == "high"
            ]
        }
        
        output_file = f"reports/analysis/{datetime.now().strftime('%Y-%m-%d')}_promotion_d.json"
        output_path = BASE_DIR / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        complete_phase(phase, output_file=output_file, items_processed=len(channels))
        log(f"D线推广分析完成: SEO健康度{channels['SEO'].get('health_rate', 0)}%, 总访问 {total_visits}, 注册 {total_signups}, CAC ¥{overall_cac}")
        return True
    except Exception as e:
        fail_phase(phase, str(e))
        return False


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
