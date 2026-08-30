"""
HealthLens 全闭环工作流调度器
统一调度6条闭环工作流线：
  A. 情报→内容闭环 (phase_1~6 + feedback_a)
  B. 用户转化闭环 (user_conversion_b)
  C. 数据资产闭环 (data_asset_c)
  D. 推广营销闭环 (promotion_d)
  E. 资金闭环 (finance_e)
  F. 项目运维闭环 (ops_health_f)

用法：
    python scheduler.py run             # 运行A线全流程
    python scheduler.py run-next        # 运行A线下一阶段
    python scheduler.py feedback        # 只运行所有反馈闭环(B~F)
    python scheduler.py feedback B      # 只运行指定闭环
    python scheduler.py status          # 查看状态
    python scheduler.py reset           # 重置A线pipeline
    python scheduler.py start-new       # 启动新一周A线pipeline
    python scheduler.py run-all         # 运行全部（A线 + 所有反馈闭环）
    python scheduler.py heal            # 只执行自愈
    python scheduler.py watchdog        # 执行看门狗检查
    python scheduler.py backup          # 执行数据库备份

修订记录 (2026-08-04) —— 闭环化改造
-----------------------------------
原调度器只是「顺序执行脚本 + 打印结果」，缺失闭环的三个关键环节：

  ❌ 失败后不重试     → 新增 max_retries 指数退避重试
  ❌ 失败后不修复     → 每轮运行前先跑自愈引擎，失败后再自愈+重试
  ❌ 失败后不通知     → 接入 alerting，失败必告警，恢复必通知

另外修正了一个致命的语义问题：原 run_all 的"全部成功"判断依赖各子脚本
的退出码，而多个子脚本（尤其 ops_health_f）无论检查结果如何都 return True，
于是「站点全挂」被打印成「全部闭环执行结束: 全部成功」。
子脚本已逐个修正为 fail-loud，这里再加一层交叉校验：即使子脚本说自己成功，
调度器也会复核关键健康指标，不一致则以健康指标为准。
"""
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# 路径设置
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "scripts" / "core"))

from state_manager import (
    get_state, save_state, reset_pipeline,
    get_next_runnable_phase, PHASES, log
)
from alerting import send_alert, resolve_alert, get_active_alerts, LEVEL_WARN, LEVEL_CRITICAL
from self_heal import run_all_heals

# ===== A线：情报→内容闭环（6阶段） =====
PHASE_SCRIPTS = {
    "collect": "scripts/phase_1_collect/run.py",
    "analyze": "scripts/phase_2_analyze/run.py",
    "decide": "scripts/phase_3_decide/run.py",
    "develop": "scripts/phase_4_develop/run.py",
    "test": "scripts/phase_5_test/run.py",
    "deploy": "scripts/phase_6_deploy/run.py",
}
PHASE_NAMES = {
    "collect": "情报收集", "analyze": "智能分析", "decide": "决策门禁",
    "develop": "开发生成", "test": "质量测试", "deploy": "部署上架",
}

# ===== 反馈闭环脚本（B~F线） =====
FEEDBACK_PIPELINES = {
    "A": {"name": "A.效果追踪反馈", "script": "scripts/phase_7_feedback/feedback_a.py"},
    "B": {"name": "B.用户转化闭环", "script": "scripts/phase_7_feedback/user_conversion_b.py"},
    "C": {"name": "C.数据资产闭环", "script": "scripts/phase_7_feedback/data_asset_c.py"},
    "D": {"name": "D.推广营销闭环", "script": "scripts/phase_7_feedback/promotion_d.py"},
    "E": {"name": "E.资金闭环",     "script": "scripts/phase_7_feedback/finance_e.py"},
    "F": {"name": "F.项目运维闭环", "script": "scripts/phase_7_feedback/ops_health_f.py"},
}

# ===== 运维任务 =====
OPS_SCRIPTS = {
    "backup": "scripts/phase_8_ops/backup_db.py",
    "watchdog": "scripts/phase_8_ops/watchdog.py",
}


def _config() -> dict:
    try:
        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"config.json 读取失败，使用默认配置: {e}", level="WARN")
        return {}


def _exec_cfg() -> dict:
    return _config().get("execution", {})


def run_script(script_path, name="", timeout=None, retries=None):
    """执行一个脚本，失败时按配置重试。

    返回 dict，而不是原来的 bool——因为「失败」需要携带原因才能被处理。
    只返回 True/False 是原系统无法自愈的根因之一：调用方拿不到任何可用于
    决策的信息。
    """
    cfg = _exec_cfg()
    timeout = timeout if timeout is not None else cfg.get("script_timeout_seconds", 300)
    retries = retries if retries is not None else cfg.get("max_retries", 2)
    delay = cfg.get("retry_delay_seconds", 30)

    full_path = BASE_DIR / script_path
    label = name or script_path

    if not full_path.exists():
        log(f"脚本不存在: {full_path}", level="ERROR")
        return {"ok": False, "reason": "script_not_found", "detail": str(full_path),
                "attempts": 0, "name": label}

    last = {"ok": False, "reason": "unknown", "detail": "", "attempts": 0, "name": label}

    for attempt in range(1, retries + 2):  # 首次 + retries 次重试
        if attempt > 1:
            backoff = delay * (2 ** (attempt - 2))  # 指数退避: 30s, 60s, 120s...
            log(f"  {label} 第 {attempt}/{retries + 1} 次尝试（等待 {backoff}s）")
            time.sleep(backoff)
        else:
            log(f"执行: {label}")

        try:
            result = subprocess.run(
                [sys.executable, str(full_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(BASE_DIR), timeout=timeout,
            )
            if result.returncode == 0:
                log(f"  {label} 成功" + (f"（第 {attempt} 次尝试）" if attempt > 1 else ""))
                return {"ok": True, "reason": "", "detail": "", "attempts": attempt, "name": label}

            stderr_tail = (result.stderr or "")[-400:]
            stdout_tail = (result.stdout or "")[-200:]
            log(f"  {label} 失败 (exit {result.returncode})", level="ERROR")
            if stderr_tail:
                log(f"  stderr: {stderr_tail}", level="ERROR")
            last = {"ok": False, "reason": f"exit_{result.returncode}",
                    "detail": stderr_tail or stdout_tail, "attempts": attempt, "name": label}

        except subprocess.TimeoutExpired:
            log(f"  {label} 超时({timeout}s)", level="ERROR")
            last = {"ok": False, "reason": "timeout", "detail": f"{timeout}s",
                    "attempts": attempt, "name": label}
        except Exception as e:
            log(f"  {label} 异常: {e}", level="ERROR")
            last = {"ok": False, "reason": "exception", "detail": str(e)[:300],
                    "attempts": attempt, "name": label}

    return last


def run_phase(phase_name):
    """执行A线单个阶段"""
    return run_script(PHASE_SCRIPTS[phase_name], name=f"A线·{PHASE_NAMES[phase_name]}")


def run_feedback_pipeline(code):
    """执行指定反馈闭环"""
    if code not in FEEDBACK_PIPELINES:
        log(f"未知闭环: {code}", level="ERROR")
        return {"ok": False, "reason": "unknown_pipeline", "detail": code, "attempts": 0, "name": code}
    pipe = FEEDBACK_PIPELINES[code]
    return run_script(pipe["script"], name=pipe["name"])


def run_all_feedback():
    """运行所有反馈闭环(B~F)"""
    log("=" * 60)
    log("运行所有反馈闭环 (B~F)")
    log("=" * 60)

    results = {}
    for code, pipe in FEEDBACK_PIPELINES.items():
        results[code] = run_script(pipe["script"], name=pipe["name"])

    failed = {c: r for c, r in results.items() if not r["ok"]}

    log("=" * 60)
    log("反馈闭环执行结束:")
    for code, r in results.items():
        icon = "✅" if r["ok"] else "❌"
        extra = "" if r["ok"] else f" ({r['reason']})"
        log(f"  {icon} {code}: {FEEDBACK_PIPELINES[code]['name']} - "
            f"{'成功' if r['ok'] else '失败'}{extra}")
    log("=" * 60)

    if failed:
        send_alert(
            level=LEVEL_WARN if len(failed) < 3 else LEVEL_CRITICAL,
            title=f"{len(failed)}/{len(results)} 条反馈闭环失败",
            message="\n".join(
                f"- {FEEDBACK_PIPELINES[c]['name']}: {r['reason']} | {str(r['detail'])[:150]}"
                for c, r in failed.items()
            ),
            context={"failed": {c: r["reason"] for c, r in failed.items()}},
            dedup_key="scheduler:feedback_failed",
        )
    else:
        resolve_alert("scheduler:feedback_failed", note="所有反馈闭环已恢复正常。")

    return results


def run_pipeline_a(allow_heal=True):
    """运行A线全流程（情报→内容→部署）

    闭环逻辑：阶段失败 → 自愈 → 重跑该阶段 → 仍失败则告警并中断。
    这是「报错→修复→重试」链条真正落地的地方。
    """
    log("=" * 60)
    log("运行A线: 情报→内容闭环")
    log("=" * 60)

    executed, succeeded = 0, 0
    failures = []
    healed_once = set()

    while True:
        next_phase = get_next_runnable_phase()
        if not next_phase:
            break

        executed += 1
        result = run_phase(next_phase)

        if result["ok"]:
            succeeded += 1
            continue

        # ---- 失败：先自愈再重跑一次该阶段 ----
        if allow_heal and _exec_cfg().get("auto_heal_enabled", True) and next_phase not in healed_once:
            healed_once.add(next_phase)
            log(f"阶段 {next_phase} 失败，启动自愈后重试", level="WARN")
            run_all_heals(verbose=False)

            retry_result = run_phase(next_phase)
            if retry_result["ok"]:
                succeeded += 1
                log(f"[闭环] 阶段 {PHASE_NAMES[next_phase]} 自愈后重跑成功")
                continue
            result = retry_result

        failures.append({"phase": next_phase, **result})
        send_alert(
            level=LEVEL_CRITICAL,
            title=f"A线阻塞于「{PHASE_NAMES[next_phase]}」",
            message=(
                f"阶段 {next_phase} 经过 {result['attempts']} 次尝试 + 自愈仍失败。\n"
                f"原因: {result['reason']}\n"
                f"详情: {str(result['detail'])[:400]}\n"
                f"A线后续阶段全部无法推进，内容生产已停止。"
            ),
            context={"phase": next_phase, "result": result},
            dedup_key=f"pipeline_a:{next_phase}_failed",
        )
        if _exec_cfg().get("fail_fast_on_phase_error", True):
            break

    state = get_state()
    ok = len(failures) == 0
    log(f"A线结束: 执行 {executed}, 成功 {succeeded}, 失败 {len(failures)}, 状态: {state['status']}")

    if ok and executed:
        for p in PHASES:
            resolve_alert(f"pipeline_a:{p}_failed")

    return {"ok": ok, "executed": executed, "succeeded": succeeded, "failures": failures}


def _crosscheck_health():
    """交叉校验：不信任子脚本的自我汇报，直接读关键健康指标。

    这是防止「系统撒谎」的最后一道防线。2026-08-03 的教训是：
    子脚本说成功，日志里却明明白白写着端点 0/4 正常。
    """
    issues = []
    state = get_state()
    metrics = state.get("feedback_metrics", {})

    ops = metrics.get("ops_health", {})
    if ops:
        if ops.get("overall") not in ("healthy", None):
            issues.append(f"运维状态={ops.get('overall')} (端点 {ops.get('endpoints_ok')}/"
                          f"{ops.get('endpoints_ok', 0) + ops.get('endpoints_error', 0)} 正常)")
        if ops.get("endpoints_error", 0) > 0:
            issues.append(f"{ops['endpoints_error']} 个端点异常")

    stuck = [t.get("task_id") for t in state.get("development_tasks", [])
             if t.get("status") in ("test_failed", "deploy_failed", "needs_manual_review")]
    if stuck:
        issues.append(f"{len(stuck)} 个任务处于失败态: {stuck[:5]}")

    active = get_active_alerts()
    crit = [k for k, v in active.items() if v.get("level") == LEVEL_CRITICAL]
    if crit:
        issues.append(f"{len(crit)} 条未解决的严重告警: {crit[:5]}")

    return issues


def _save_run_record(record):
    """把每次运行落盘，形成可审计的运行史。

    原系统只有日志文本，无法回答「过去 30 天成功率多少」这种问题。
    """
    runs_dir = BASE_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    fname = runs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    state = get_state()
    history = state.setdefault("run_history", [])
    history.append({
        "run_id": record["run_id"],
        "started_at": record["started_at"],
        "finished_at": record["finished_at"],
        "verdict": record["verdict"],
        "failed_count": record["failed_count"],
    })
    state["run_history"] = history[-60:]  # 保留最近 60 次
    save_state(state)
    return fname


def run_all():
    """运行全部：自愈 → A线 → A线反馈 → B~F反馈闭环 → 交叉校验 → 汇总告警"""
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    started = datetime.now()

    log("=" * 60)
    log(f"运行全部闭环工作流 [{run_id}]")
    log("=" * 60)

    # 0. 运行前自愈：清理上一轮遗留的卡死与失败态
    heal_summary = run_all_heals(verbose=True)

    # 1. A线主流程
    a_result = run_pipeline_a()

    # 2. A线效果反馈
    feedback_a = run_feedback_pipeline("A")

    # 3. B~F反馈闭环
    bf_results = run_all_feedback()

    # 4. 交叉校验（关键：不采信子脚本的自我汇报）
    health_issues = _crosscheck_health()

    failed_items = []
    if not a_result["ok"]:
        failed_items += [f"A线·{PHASE_NAMES.get(f['phase'], f['phase'])}({f['reason']})"
                         for f in a_result["failures"]]
    if not feedback_a["ok"]:
        failed_items.append(f"A线反馈({feedback_a['reason']})")
    failed_items += [f"{c}线({r['reason']})" for c, r in bf_results.items() if not r["ok"]]

    if failed_items:
        verdict = "FAILED"
    elif health_issues:
        # 所有脚本都退出 0，但健康指标说有问题——这正是原系统会误报"全部成功"的场景
        verdict = "DEGRADED"
    else:
        verdict = "SUCCESS"

    finished = datetime.now()
    record = {
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": int((finished - started).total_seconds()),
        "verdict": verdict,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
        "health_issues": health_issues,
        "heal_summary": heal_summary,
        "pipeline_a": a_result,
        "feedback_a": feedback_a,
        "feedback_bf": bf_results,
    }
    record_path = _save_run_record(record)

    log("=" * 60)
    if verdict == "SUCCESS":
        log("全部闭环执行结束: 全部成功")
        resolve_alert("scheduler:run_failed", note="流水线已恢复全绿。")
    elif verdict == "DEGRADED":
        log("全部闭环执行结束: 脚本均退出0，但健康校验发现问题 ↓", level="ERROR")
        for i in health_issues:
            log(f"    ⚠ {i}", level="ERROR")
        send_alert(
            level=LEVEL_WARN,
            title="流水线退化：脚本报成功但健康校验不通过",
            message="所有脚本退出码为 0，但交叉校验发现:\n" +
                    "\n".join(f"- {i}" for i in health_issues) +
                    "\n\n这种「脚本说成功、指标说有病」的不一致，通常意味着"
                    "某个子脚本仍在 fail-open。",
            context={"health_issues": health_issues},
            dedup_key="scheduler:degraded",
        )
    else:
        log(f"全部闭环执行结束: {len(failed_items)} 项失败 ↓", level="ERROR")
        for i in failed_items:
            log(f"    ✗ {i}", level="ERROR")
        for i in health_issues:
            log(f"    ⚠ {i}", level="ERROR")
        send_alert(
            level=LEVEL_CRITICAL,
            title=f"流水线运行失败: {len(failed_items)} 项",
            message="失败项:\n" + "\n".join(f"- {i}" for i in failed_items) +
                    (("\n\n健康问题:\n" + "\n".join(f"- {i}" for i in health_issues))
                     if health_issues else ""),
            context={"run_id": run_id, "record": str(record_path)},
            dedup_key="scheduler:run_failed",
        )

    log(f"运行记录: {record_path.relative_to(BASE_DIR)}")
    log(f"结论: {verdict} | 耗时 {record['duration_seconds']}s")
    log("=" * 60)

    return verdict == "SUCCESS"


def print_status():
    """打印完整状态"""
    state = get_state()

    print("\n" + "=" * 60)
    print(f"  Pipeline ID: {state['pipeline_id']}")
    print(f"  总体状态: {state['status']}")
    print("=" * 60)

    print("\n  [A线] 情报→内容闭环:")
    for phase in PHASES:
        info = state["phases"].get(phase, {})
        status = info.get("status", "pending")
        icon = {"pending": "⬜", "running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "❓")
        items = info.get("items_processed", 0)
        print(f"    {icon} {PHASE_NAMES[phase]}: {status}" + (f" ({items}项)" if items else ""))

    metrics = state.get("feedback_metrics", {})
    if metrics:
        print("\n  反馈指标:")
        for key, value in metrics.items():
            if isinstance(value, dict):
                ts = value.get("checked_at", "")[:16] if value.get("checked_at") else ""
                summary = ", ".join(f"{k}={v}" for k, v in value.items()
                                    if k != "checked_at" and isinstance(v, (int, float, str, bool)))
                print(f"    [{key}] {ts} | {summary[:70]}")

    tasks = state.get("development_tasks", [])
    if tasks:
        print(f"\n  开发任务: {len(tasks)} 项")
        for t in tasks[:5]:
            print(f"    - [{t.get('status', '?')}] {t.get('title', '')[:40]}")

    deployments = state.get("deployment_history", [])
    if deployments:
        print(f"\n  部署记录: {len(deployments)} 次")

    # 活跃告警——状态面板必须显示这个，否则告警等于没有
    active = get_active_alerts()
    print(f"\n  活跃告警: {len(active)} 条")
    for key, item in list(active.items())[:8]:
        icon = "🔴" if item.get("level") == LEVEL_CRITICAL else "⚠️"
        print(f"    {icon} {item.get('title', key)} "
              f"(×{item.get('count', 1)}, 自 {item.get('first_seen', '')[:16]})")

    history = state.get("run_history", [])
    if history:
        recent = history[-5:]
        print(f"\n  最近运行 ({len(history)} 次记录):")
        for r in reversed(recent):
            v = r.get("verdict", "?")
            icon = {"SUCCESS": "✅", "DEGRADED": "⚠️", "FAILED": "❌"}.get(v, "❓")
            print(f"    {icon} {r.get('started_at', '')[:19]} {v}"
                  + (f" ({r.get('failed_count')} 项失败)" if r.get("failed_count") else ""))

    print()


def main():
    parser = argparse.ArgumentParser(description="HealthLens 全闭环工作流调度器")
    parser.add_argument("command", choices=[
        "run", "run-next", "feedback", "run-all", "status",
        "reset", "start-new", "heal", "watchdog", "backup",
    ])
    parser.add_argument("target", nargs="?", default="all",
                        help="可选: 指定反馈闭环代码(A/B/C/D/E/F)")

    args = parser.parse_args()

    if args.command == "run":
        result = run_pipeline_a()
        print_status()
        sys.exit(0 if result["ok"] else 1)

    elif args.command == "run-next":
        next_p = get_next_runnable_phase()
        if next_p:
            result = run_phase(next_p)
            ok = result["ok"]
        else:
            log("A线没有可执行阶段")
            ok = True
        print_status()
        sys.exit(0 if ok else 1)

    elif args.command == "feedback":
        if args.target == "all":
            results = run_all_feedback()
            ok = all(r["ok"] for r in results.values())
        elif args.target.upper() in FEEDBACK_PIPELINES:
            ok = run_feedback_pipeline(args.target.upper())["ok"]
        else:
            log(f"未知闭环: {args.target}，可选: {', '.join(FEEDBACK_PIPELINES.keys())}")
            ok = False
        print_status()
        sys.exit(0 if ok else 1)

    elif args.command == "run-all":
        success = run_all()
        print_status()
        sys.exit(0 if success else 1)

    elif args.command == "status":
        print_status()

    elif args.command == "heal":
        summary = run_all_heals()
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    elif args.command == "watchdog":
        result = run_script(OPS_SCRIPTS["watchdog"], name="看门狗")
        sys.exit(0 if result["ok"] else 1)

    elif args.command == "backup":
        result = run_script(OPS_SCRIPTS["backup"], name="数据库备份", timeout=1800, retries=1)
        sys.exit(0 if result["ok"] else 1)

    elif args.command == "reset":
        reset_pipeline()
        log("A线 Pipeline 已重置")
        print_status()

    elif args.command == "start-new":
        reset_pipeline()
        log("新一周 A线 Pipeline 已启动")
        print_status()


if __name__ == "__main__":
    main()
