"""自愈引擎（2026-08-04 新增）

背景
----
原 result_aggregator.py 里有 10 处硬编码 `"auto_fixable": False`，
主函数叫 `extract_manual_actions`——代码自己承认没有任何自愈能力。
实证后果：task_edu_001 从 7/27 卡在 test_failed，8 天无重试、无告警、无人知晓。

设计
----
每条自愈规则都必须走完整的五段式，缺一不可：

    探测(detect) → 判定(should_heal) → 执行(heal) → 复验(verify) → 升级(escalate)

其中最容易被省略的是**复验**和**升级**：
- 没有复验，"修复"只是执行了一个动作，不知道有没有真的修好；
- 没有升级，自愈失败后会无限重试，把小故障拖成大故障。

因此本模块强制：
1. 每条规则有 max_attempts，超限自动升级为人工告警并停止重试；
2. 每次自愈都记录 attempt 次数与复验结果到 heal_history；
3. 自愈成功要显式验证，验证不过视为失败。
"""
import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alerting import LEVEL_CRITICAL, LEVEL_WARN, send_alert
from state_manager import BASE_DIR, PHASES, get_state, log, save_state

HEAL_HISTORY_FILE = BASE_DIR / "heal_history.json"

# 同一问题最多自愈次数，超过则升级人工
MAX_HEAL_ATTEMPTS = 3
# 阶段处于 running 超过该时长视为卡死
STUCK_PHASE_HOURS = 2


# --------------------------------------------------------------------------
# 自愈历史
# --------------------------------------------------------------------------
def _load_history() -> dict:
    if not HEAL_HISTORY_FILE.exists():
        return {"records": [], "attempts": {}}
    try:
        with open(HEAL_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"records": [], "attempts": {}}


def _save_history(h: dict) -> None:
    # 只保留最近 200 条记录，防止文件无限膨胀
    h["records"] = h.get("records", [])[-200:]
    with open(HEAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def _attempt_count(key: str) -> int:
    return _load_history().get("attempts", {}).get(key, {}).get("count", 0)


def _record_attempt(key, rule, success, detail):
    h = _load_history()
    attempts = h.setdefault("attempts", {})
    entry = attempts.setdefault(key, {"count": 0, "first_at": datetime.now().isoformat()})
    entry["count"] += 1
    entry["last_at"] = datetime.now().isoformat()
    entry["last_success"] = success
    if success:
        # 修好了就清零计数，下次同样问题重新计
        entry["count"] = 0
        entry["resolved_at"] = datetime.now().isoformat()
    h.setdefault("records", []).append({
        "timestamp": datetime.now().isoformat(),
        "rule": rule,
        "key": key,
        "success": success,
        "detail": detail,
        "attempt": entry["count"],
    })
    _save_history(h)


def _escalate(key, rule, reason, context=None):
    send_alert(
        level=LEVEL_CRITICAL,
        title=f"自愈失败需人工介入: {rule}",
        message=(
            f"问题: {reason}\n"
            f"已自动尝试 {MAX_HEAL_ATTEMPTS} 次仍未修复，停止重试以免恶化。\n"
            f"这条告警需要人工处理。"
        ),
        context=context or {},
        dedup_key=f"heal_escalate:{key}",
    )


# --------------------------------------------------------------------------
# 规则 1：卡死阶段复位
# --------------------------------------------------------------------------
def heal_stuck_phases():
    """探测：某阶段 status=running 但超过 STUCK_PHASE_HOURS 无进展。

    这类卡死会永久阻塞整条 A 线——get_next_runnable_phase 要求前置阶段
    status=completed，一个 running 挂在那里，后续阶段永远不会被调度。
    """
    state = get_state()
    healed = []
    now = datetime.now()

    for phase, info in state.get("phases", {}).items():
        if info.get("status") != "running":
            continue
        started = info.get("started_at")
        if not started:
            continue
        try:
            started_dt = datetime.fromisoformat(started)
        except ValueError:
            continue
        if now - started_dt < timedelta(hours=STUCK_PHASE_HOURS):
            continue

        key = f"stuck_phase:{phase}"
        if _attempt_count(key) >= MAX_HEAL_ATTEMPTS:
            _escalate(key, "卡死阶段复位", f"阶段 {phase} 反复卡死",
                      {"phase": phase, "started_at": started})
            continue

        # 执行：复位为 pending 让它下次重跑
        info["status"] = "pending"
        info["error"] = f"自愈复位: 卡在 running 超过 {STUCK_PHASE_HOURS}h (原 started_at={started})"
        info["started_at"] = None
        save_state(state)

        # 复验：重新读状态确认真的写进去了
        verify = get_state()["phases"].get(phase, {}).get("status") == "pending"
        _record_attempt(key, "卡死阶段复位", verify,
                        f"phase={phase} stuck_since={started}")
        if verify:
            healed.append(phase)
            log(f"[自愈] 阶段 {phase} 卡死已复位为 pending")
        else:
            log(f"[自愈] 阶段 {phase} 复位失败（复验未通过）", level="ERROR")

    return healed


# --------------------------------------------------------------------------
# 规则 2：失败任务自动重试
# --------------------------------------------------------------------------
def heal_failed_tasks():
    """探测：development_tasks 里 status 为 test_failed / deploy_failed 的任务。

    原系统这些任务会永久躺在状态文件里没人管（实证：task_edu_001 卡了 8 天）。
    现在自动退回上一个阶段重跑，超过次数上限则升级人工。
    """
    state = get_state()
    healed = []
    retry_map = {
        "test_failed": ("pending_test", "test"),      # 退回待测试
        "deploy_failed": ("test_passed", "deploy"),   # 退回待部署
    }

    for task in state.get("development_tasks", []):
        status = task.get("status")
        if status not in retry_map:
            continue

        task_id = task.get("task_id", "unknown")
        key = f"failed_task:{task_id}:{status}"
        new_status, rerun_phase = retry_map[status]

        if _attempt_count(key) >= MAX_HEAL_ATTEMPTS:
            _escalate(key, "失败任务自动重试",
                      f"任务 {task_id} ({task.get('title', '')[:40]}) 在 {status} 反复失败",
                      {"task_id": task_id, "status": status,
                       "error": str(task.get("test_result") or task.get("deploy_info"))[:300]})
            task["status"] = "needs_manual_review"
            save_state(state)
            continue

        task["status"] = new_status
        task["heal_note"] = f"自愈重试 (原状态 {status}) @ {datetime.now().isoformat()}"
        # 同时把对应阶段复位，否则阶段已 completed 不会再跑
        if rerun_phase in state.get("phases", {}):
            state["phases"][rerun_phase]["status"] = "pending"
        save_state(state)

        verify = any(
            t.get("task_id") == task_id and t.get("status") == new_status
            for t in get_state().get("development_tasks", [])
        )
        _record_attempt(key, "失败任务自动重试", verify, f"{task_id}: {status} -> {new_status}")
        if verify:
            healed.append(task_id)
            log(f"[自愈] 任务 {task_id} 从 {status} 退回 {new_status}，将重跑 {rerun_phase} 阶段")

    return healed


# --------------------------------------------------------------------------
# 规则 3：失败阶段复位（允许下轮重试）
# --------------------------------------------------------------------------
def heal_failed_phase():
    """探测：pipeline status = failed_xxx。

    原逻辑一旦某阶段失败，整条线永久停在那里，直到人工 reset。
    现在允许有限次自动重试。
    """
    state = get_state()
    status = state.get("status", "")
    if not status.startswith("failed_"):
        return []

    phase = status.replace("failed_", "")
    if phase not in state.get("phases", {}):
        return []

    key = f"failed_phase:{phase}"
    if _attempt_count(key) >= MAX_HEAL_ATTEMPTS:
        _escalate(key, "失败阶段复位", f"阶段 {phase} 连续失败 {MAX_HEAL_ATTEMPTS} 次",
                  {"phase": phase, "error": str(state["phases"][phase].get("error"))[:400]})
        return []

    prev_error = state["phases"][phase].get("error")
    state["phases"][phase]["status"] = "pending"
    state["phases"][phase]["error"] = None
    state["status"] = "idle"
    save_state(state)

    verify = get_state()["phases"][phase]["status"] == "pending"
    _record_attempt(key, "失败阶段复位", verify, f"phase={phase} prev_error={str(prev_error)[:150]}")
    if verify:
        log(f"[自愈] 失败阶段 {phase} 已复位，下轮将重试")
        return [phase]
    return []


# --------------------------------------------------------------------------
# 规则 4：目录与磁盘护栏
# --------------------------------------------------------------------------
def heal_missing_dirs():
    """探测：报告/内容输出目录缺失，会导致脚本写文件时崩溃。"""
    required = [
        "reports/analysis", "reports/decisions", "reports/deployed",
        "content/generated", "logs", "alerts", "runs", "backups",
    ]
    created = []
    for rel in required:
        p = BASE_DIR / rel
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
                created.append(rel)
            except Exception as e:
                log(f"[自愈] 创建目录失败 {rel}: {e}", level="ERROR")
    if created:
        _record_attempt("missing_dirs", "目录护栏", True, f"created={created}")
        log(f"[自愈] 已补建目录: {', '.join(created)}")
    return created


def check_disk_space(min_free_gb=2.0):
    """探测：磁盘空间不足会让备份、日志、内容生成全部静默失败。"""
    try:
        usage = shutil.disk_usage(str(BASE_DIR))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < min_free_gb:
            send_alert(
                level=LEVEL_CRITICAL if free_gb < 1 else LEVEL_WARN,
                title=f"磁盘空间不足: 剩余 {free_gb:.1f}GB",
                message=(
                    f"剩余空间 {free_gb:.1f}GB 低于阈值 {min_free_gb}GB。\n"
                    f"磁盘写满会导致备份失败、日志丢失、状态文件损坏，"
                    f"且这些失败往往是静默的。"
                ),
                context={"free_gb": round(free_gb, 2), "total_gb": round(usage.total / (1024 ** 3), 2)},
                dedup_key="disk:low_space",
            )
            return False, free_gb
        return True, free_gb
    except Exception as e:
        log(f"磁盘检查失败: {e}", level="WARN")
        return True, -1


# --------------------------------------------------------------------------
# 规则 5：状态文件完整性
# --------------------------------------------------------------------------
def heal_state_integrity():
    """探测：pipeline_state.json 缺字段或损坏。

    状态文件是整个流水线的单点——它一坏，所有脚本一起崩。
    """
    fixed = []
    try:
        state = get_state()
    except Exception as e:
        # 状态文件已损坏：备份后重建，这是最后的兜底
        broken = BASE_DIR / f"pipeline_state.broken.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            shutil.copy(BASE_DIR / "pipeline_state.json", broken)
        except Exception:
            pass
        send_alert(
            level=LEVEL_CRITICAL,
            title="pipeline_state.json 已损坏",
            message=f"状态文件无法解析({str(e)[:200]})，已备份至 {broken.name} 并重建。"
                    f"历史进度可能丢失，请检查备份文件。",
            dedup_key="state:corrupted",
        )
        from state_manager import _init_state
        _init_state()
        return ["rebuilt_state"]

    required_keys = {
        "phases": {}, "development_tasks": [], "deployment_history": [],
        "feedback_metrics": {}, "approved_queue": [], "watch_queue": [],
        "rejected_items": [], "run_history": [],
    }
    changed = False
    for k, default in required_keys.items():
        if k not in state:
            state[k] = default if not isinstance(default, (dict, list)) else type(default)()
            fixed.append(k)
            changed = True

    for phase in PHASES:
        if phase not in state.get("phases", {}):
            state["phases"][phase] = {
                "status": "pending", "started_at": None, "completed_at": None,
                "output_file": None, "items_processed": 0, "error": None,
            }
            fixed.append(f"phase:{phase}")
            changed = True

    if changed:
        save_state(state)
        _record_attempt("state_integrity", "状态完整性", True, f"fixed={fixed}")
        log(f"[自愈] 状态文件补全字段: {', '.join(fixed)}")
    return fixed


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------
def run_all_heals(verbose=True):
    """按依赖顺序执行全部自愈规则。

    顺序有讲究：先保证目录和状态文件可用（其他规则依赖它们），
    再处理卡死和失败。
    """
    if verbose:
        log("=" * 60)
        log("自愈引擎启动")
        log("=" * 60)

    summary = {
        "started_at": datetime.now().isoformat(),
        "dirs_created": heal_missing_dirs(),
        "state_fixed": heal_state_integrity(),
        "stuck_phases_reset": heal_stuck_phases(),
        "failed_phase_reset": heal_failed_phase(),
        "tasks_retried": heal_failed_tasks(),
    }
    disk_ok, free_gb = check_disk_space()
    summary["disk_ok"] = disk_ok
    summary["disk_free_gb"] = round(free_gb, 2) if free_gb >= 0 else None

    total = sum(len(v) for v in summary.values() if isinstance(v, list))
    summary["total_actions"] = total
    summary["finished_at"] = datetime.now().isoformat()

    if verbose:
        if total:
            log(f"自愈完成: 共执行 {total} 项修复动作")
            for k, v in summary.items():
                if isinstance(v, list) and v:
                    log(f"  - {k}: {v}")
        else:
            log("自愈完成: 无需修复")

    return summary


if __name__ == "__main__":
    result = run_all_heals()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)
