"""T7 心跳看门狗（2026-08-04 新增）

要解决的问题
------------
原系统所有监控都是「任务跑起来了才会检查」。这留下一个致命盲区：

    如果任务本身死了 / 电脑关机 / 定时器没触发 —— 没有任何东西会发现。

实证：auto-pipeline 跑在本机 Windows，8-03 之后就没再执行过；
Celery Beat 根本没部署，9 个定时任务从未运行。这两件事都没有任何机制能发现。

看门狗的核心思路是**反向监控**：不检查「任务做得对不对」，
而是检查「任务是不是本该跑却没跑」。它是唯一能发现「沉默故障」的组件。

检查项
------
1. 流水线新鲜度  —— 上次成功运行距今多久
2. 各闭环新鲜度  —— 每条线的 checked_at 是否超期
3. 备份新鲜度    —— 多久没有成功备份（单独列，因为最危险）
4. Beat 心跳     —— healthlens 后端 celery beat 是否存活
5. 站点可用性    —— 端点探测（与 F 线独立，双保险）
6. 活跃告警堆积  —— 长期未解决的告警本身就是一种故障

看门狗必须是**最简单、最不可能自己出错**的组件，
因此这里刻意不依赖数据库、不依赖网络（除站点探测外），只读本地状态文件。
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from alerting import (
    LEVEL_CRITICAL,
    LEVEL_WARN,
    get_active_alerts,
    resolve_alert,
    send_alert,
)
from state_manager import BASE_DIR, get_state, log


def _cfg() -> dict:
    with open(BASE_DIR / "config.json", encoding="utf-8") as f:
        return json.load(f)


def _hours_since(iso_str):
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", ""))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return (datetime.now() - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# 检查 1: 流水线运行新鲜度
# --------------------------------------------------------------------------
def check_pipeline_freshness(state, thresholds):
    findings = []
    limit = thresholds.get("pipeline_run", 30)

    history = state.get("run_history", [])
    if not history:
        findings.append({
            "severity": "warn",
            "item": "流水线运行记录",
            "detail": "从未有过带记录的完整运行。若这是首次部署可忽略，"
                      "否则说明调度从未真正执行。",
        })
        return findings

    last = history[-1]
    hours = _hours_since(last.get("started_at"))
    if hours is None:
        findings.append({"severity": "warn", "item": "流水线运行记录",
                         "detail": f"最近记录时间无法解析: {last.get('started_at')}"})
    elif hours > limit:
        findings.append({
            "severity": "critical" if hours > limit * 2 else "warn",
            "item": "流水线已停跑",
            "detail": f"距上次运行 {hours:.1f} 小时（阈值 {limit}h）。"
                      f"最近结论: {last.get('verdict')}。"
                      f"常见原因：本机关机 / 计划任务被禁用 / Python 环境损坏。",
        })

    # 连续失败检测：比单次失败更值得告警
    recent = history[-3:]
    if len(recent) >= 3 and all(r.get("verdict") == "FAILED" for r in recent):
        findings.append({
            "severity": "critical",
            "item": "连续失败",
            "detail": "最近 3 次运行全部失败，自愈机制未能恢复，需人工介入。",
        })
    return findings


# --------------------------------------------------------------------------
# 检查 2: 各闭环指标新鲜度
# --------------------------------------------------------------------------
def check_metric_freshness(state, thresholds):
    findings = []
    metrics = state.get("feedback_metrics", {})
    default_limit = 30

    for key, limit in thresholds.items():
        if key in ("pipeline_run",):
            continue
        m = metrics.get(key)
        if not m:
            continue
        hours = _hours_since(m.get("checked_at"))
        if hours is not None and hours > limit:
            findings.append({
                "severity": "warn",
                "item": f"{key} 数据陈旧",
                "detail": f"距上次更新 {hours:.1f} 小时（阈值 {limit}h），该闭环可能已停止运行。",
            })

    for key, m in metrics.items():
        if key in thresholds or not isinstance(m, dict):
            continue
        hours = _hours_since(m.get("checked_at"))
        if hours is not None and hours > default_limit:
            findings.append({
                "severity": "warn",
                "item": f"{key} 数据陈旧",
                "detail": f"距上次更新 {hours:.1f} 小时（默认阈值 {default_limit}h）。",
            })
    return findings


# --------------------------------------------------------------------------
# 检查 3: 备份新鲜度（单列，因为后果最严重）
# --------------------------------------------------------------------------
def check_backup_freshness(state, thresholds):
    findings = []
    limit = thresholds.get("backup", 30)
    backup = state.get("feedback_metrics", {}).get("backup")

    if not backup:
        findings.append({
            "severity": "critical",
            "item": "从未备份",
            "detail": "系统中不存在任何成功备份记录。健康检测数据一旦丢失不可恢复。",
        })
        return findings

    if backup.get("status") != "success":
        findings.append({
            "severity": "critical",
            "item": "最近备份未成功",
            "detail": f"最近一次备份状态为 {backup.get('status')}。",
        })

    hours = _hours_since(backup.get("checked_at"))
    if hours is not None and hours > limit:
        findings.append({
            "severity": "critical",
            "item": "备份已过期",
            "detail": f"距上次备份 {hours:.1f} 小时（阈值 {limit}h）。"
                      f"当前故障窗口内的数据没有任何保护。",
        })
    return findings


# --------------------------------------------------------------------------
# 检查 4: Celery Beat 心跳
# --------------------------------------------------------------------------
def check_beat_heartbeat():
    """读取后端写的心跳文件，判断 celery beat 是否存活。

    路径优先级：环境变量 > 容器挂载目录 > 项目 data 目录。
    找不到心跳文件不一定是故障（可能后端还没部署），
    因此区分 missing（warn）与 stale（critical）。
    """
    findings = []
    candidates = [
        BASE_DIR.parent / "healthlens" / "data" / "heartbeat.json",
        Path("/app/data/heartbeat.json"),
    ]
    hb_file = next((p for p in candidates if p.exists()), None)

    if hb_file is None:
        findings.append({
            "severity": "warn",
            "item": "Beat 心跳文件不存在",
            "detail": "未找到 heartbeat.json。若后端尚未部署 beat 服务属预期；"
                      "若已部署，说明 beat 或 worker 未正常工作。"
                      f"查找路径: {[str(p) for p in candidates]}",
        })
        return findings

    try:
        with open(hb_file, encoding="utf-8") as f:
            hb = json.load(f)
        hours = _hours_since(hb.get("timestamp"))
        if hours is None:
            findings.append({"severity": "warn", "item": "Beat 心跳异常",
                             "detail": f"心跳时间戳无法解析: {hb.get('timestamp')}"})
        elif hours > 0.5:  # 心跳间隔 10 分钟，超过 30 分钟即异常
            findings.append({
                "severity": "critical",
                "item": "Beat 心跳中断",
                "detail": f"距上次心跳 {hours * 60:.0f} 分钟（正常应 ≤10 分钟）。"
                          f"这说明 celery beat 或 worker 已停止，"
                          f"所有后端定时任务均未执行。",
            })
    except Exception as e:
        findings.append({"severity": "warn", "item": "Beat 心跳读取失败",
                         "detail": str(e)[:200]})
    return findings


# --------------------------------------------------------------------------
# 检查 5: 站点可用性（与 F 线独立的第二双眼睛）
# --------------------------------------------------------------------------
def check_site(endpoints):
    findings = []
    down = []
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HealthLens-Watchdog/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                if not (200 <= resp.status < 300):
                    down.append(f"{url}({resp.status})")
        except urllib.error.HTTPError as e:
            down.append(f"{url}({e.code})")
        except (urllib.error.URLError, TimeoutError):
            down.append(f"{url}(不可达)")
        except Exception as e:
            down.append(f"{url}({str(e)[:40]})")

    if down:
        findings.append({
            "severity": "critical" if len(down) == len(endpoints) else "warn",
            "item": f"站点端点异常 {len(down)}/{len(endpoints)}",
            "detail": "; ".join(down),
        })
    return findings


# --------------------------------------------------------------------------
# 检查 6: 告警堆积
# --------------------------------------------------------------------------
def check_alert_backlog():
    """长期不消失的告警本身就是一种故障——它会训练人忽略所有告警。"""
    findings = []
    active = get_active_alerts()
    for key, item in active.items():
        if key.startswith("watchdog:"):
            continue
        hours = _hours_since(item.get("first_seen"))
        if hours is not None and hours > 72:
            findings.append({
                "severity": "warn",
                "item": "告警长期未解决",
                "detail": f"「{item.get('title', key)}」已持续 {hours / 24:.1f} 天，"
                          f"出现 {item.get('count', 1)} 次仍未消失。",
            })
    return findings


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run():
    cfg = _cfg()
    wd_cfg = cfg.get("watchdog", {})
    if not wd_cfg.get("enabled", True):
        log("看门狗已在配置中禁用")
        return True

    thresholds = wd_cfg.get("max_staleness_hours", {})
    endpoints = wd_cfg.get("site_endpoints", [])

    log("=" * 60)
    log("T7 看门狗巡检")
    log("=" * 60)

    state = get_state()
    findings = []
    findings += check_pipeline_freshness(state, thresholds)
    findings += check_metric_freshness(state, thresholds)
    findings += check_backup_freshness(state, thresholds)
    findings += check_beat_heartbeat()
    if endpoints:
        findings += check_site(endpoints)
    findings += check_alert_backlog()

    critical = [f for f in findings if f["severity"] == "critical"]
    warns = [f for f in findings if f["severity"] == "warn"]

    report = {
        "checked_at": datetime.now().isoformat(),
        "total_findings": len(findings),
        "critical": len(critical),
        "warn": len(warns),
        "findings": findings,
        "verdict": "critical" if critical else ("warn" if warns else "ok"),
    }

    rep_dir = BASE_DIR / "reports" / "analysis"
    rep_dir.mkdir(parents=True, exist_ok=True)
    with open(rep_dir / f"{datetime.now().strftime('%Y-%m-%d')}_watchdog.json",
              "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    for f in findings:
        icon = "🔴" if f["severity"] == "critical" else "⚠️"
        log(f"  {icon} [{f['item']}] {f['detail']}",
            level="ERROR" if f["severity"] == "critical" else "WARN")

    if critical:
        send_alert(
            level=LEVEL_CRITICAL,
            title=f"看门狗发现 {len(critical)} 项严重问题",
            message="\n".join(f"- [{f['item']}] {f['detail']}" for f in critical),
            context={"findings": critical},
            dedup_key="watchdog:critical",
        )
    else:
        resolve_alert("watchdog:critical", note="看门狗严重项已全部消除。")

    if warns:
        send_alert(
            level=LEVEL_WARN,
            title=f"看门狗发现 {len(warns)} 项警告",
            message="\n".join(f"- [{f['item']}] {f['detail']}" for f in warns),
            context={"findings": warns},
            dedup_key="watchdog:warn",
        )
    else:
        resolve_alert("watchdog:warn")

    if not findings:
        log("看门狗巡检通过：无异常")

    log(f"结论: {report['verdict']} ({len(critical)} 严重 / {len(warns)} 警告)")
    log("=" * 60)

    # 有严重问题时退出码非 0，让上层调度/计划任务也能感知
    return len(critical) == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
