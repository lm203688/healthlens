"""
ops_monitor.py — 运行监控。

采集系统健康指标：内存/磁盘/进程、管线运行次数、错误率、Skill 状态。
提供健康检查端点和告警阈值。

对外 API:
    get_system_health()
    get_pipeline_metrics()
    get_skill_status()
    get_alerts()
    run_ops_check(inputs=None)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # type: ignore

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
OPS_PATH = ROOT / "data" / "ops_metrics.json"

# 告警阈值
CPU_WARN = 80.0
CPU_CRIT = 95.0
MEM_WARN = 80.0
MEM_CRIT = 95.0
DISK_WARN = 85.0
DISK_CRIT = 95.0
ERROR_RATE_WARN = 5.0  # %


@dataclass
class HealthStatus:
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    criticals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _get_cpu() -> dict:
    if psutil is None:
        return {"percent": -1, "cores": os.cpu_count() or 1, "note": "psutil not available"}
    cpu = psutil.cpu_percent(interval=0.5)
    return {
        "percent": round(cpu, 1),
        "cores": psutil.cpu_count() or os.cpu_count() or 1,
        "load": os.getloadavg() if hasattr(os, "getloadavg") else None,
    }


def _get_memory() -> dict:
    if psutil is None:
        return {"percent": -1, "total": -1, "available": -1, "note": "psutil not available"}
    mem = psutil.virtual_memory()
    return {
        "percent": round(mem.percent, 1),
        "total_gb": round(mem.total / 1024**3, 1),
        "available_gb": round(mem.available / 1024**3, 1),
        "used_gb": round(mem.used / 1024**3, 1),
    }


def _get_disk(path: str = ".") -> dict:
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / 1024**3, 1),
        "used_gb": round(usage.used / 1024**3, 1),
        "free_gb": round(usage.free / 1024**3, 1),
        "percent": round(usage.used / usage.total * 100, 1),
    }


def _check_thresholds(value: float, warn: float, crit: float, label: str, health: HealthStatus) -> None:
    if value >= crit:
        health.criticals.append(f"{label} CRITICAL: {value}%")
        health.ok = False
    elif value >= warn:
        health.warnings.append(f"{label} WARNING: {value}%")


def get_system_health() -> dict:
    """系统健康检查：CPU / 内存 / 磁盘 / Python 版本。"""
    health = HealthStatus()
    cpu = _get_cpu()
    mem = _get_memory()
    disk = _get_disk(str(ROOT))

    if cpu["percent"] >= 0:
        _check_thresholds(cpu["percent"], CPU_WARN, CPU_CRIT, "CPU", health)
    if mem["percent"] >= 0:
        _check_thresholds(mem["percent"], MEM_WARN, MEM_CRIT, "MEM", health)
    _check_thresholds(disk["percent"], DISK_WARN, DISK_CRIT, "DISK", health)

    return {
        "status": "healthy" if health.ok else "degraded",
        "cpu": cpu,
        "memory": mem,
        "disk": disk,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "warnings": health.warnings,
        "criticals": health.criticals,
    }


def _load_metrics() -> dict:
    if not OPS_PATH.exists():
        return {"pipeline_runs": [], "errors": [], "last_updated": None}
    try:
        with open(OPS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"pipeline_runs": [], "errors": [], "last_updated": None}


def _save_metrics(metrics: dict) -> None:
    OPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def record_pipeline_run(phase: str, duration_ms: float, success: bool) -> None:
    """记录一次管线运行。"""
    metrics = _load_metrics()
    entry = {
        "phase": phase,
        "timestamp": time.time(),
        "duration_ms": round(duration_ms, 1),
        "success": success,
    }
    metrics.setdefault("pipeline_runs", []).append(entry)
    # 保留最近 1000 条
    if len(metrics["pipeline_runs"]) > 1000:
        metrics["pipeline_runs"] = metrics["pipeline_runs"][-1000:]
    if not success:
        metrics.setdefault("errors", []).append(entry)
    metrics["last_updated"] = time.time()
    _save_metrics(metrics)


def get_pipeline_metrics() -> dict:
    """管线运行指标：总次数、成功率、平均耗时、错误列表。"""
    metrics = _load_metrics()
    runs = metrics.get("pipeline_runs", [])
    total = len(runs)
    successes = sum(1 for r in runs if r.get("success"))
    durations = [r.get("duration_ms", 0) for r in runs if r.get("duration_ms")]
    by_phase: dict[str, dict] = {}

    for r in runs:
        p = r.get("phase", "unknown")
        if p not in by_phase:
            by_phase[p] = {"count": 0, "success": 0, "total_ms": 0}
        by_phase[p]["count"] += 1
        by_phase[p]["total_ms"] += r.get("duration_ms", 0)
        if r.get("success"):
            by_phase[p]["success"] += 1

    # 计算各阶段平均耗时和成功率
    for p in by_phase:
        c = by_phase[p]["count"]
        by_phase[p]["avg_ms"] = round(by_phase[p]["total_ms"] / c, 1) if c else 0
        by_phase[p]["success_rate"] = round(by_phase[p]["success"] / c * 100, 1) if c else 0
        del by_phase[p]["total_ms"]

    return {
        "total_runs": total,
        "success_count": successes,
        "error_count": total - successes,
        "success_rate_pct": round(successes / total * 100, 1) if total else 0,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "by_phase": by_phase,
        "recent_errors": metrics.get("errors", [])[-10:],
    }


def get_skill_status() -> dict[str, Any]:
    """检查所有 Skill 状态。"""
    skills_dir = ROOT / "skills"
    if not skills_dir.exists():
        return {"skills": [], "total": 0}
    skills = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        skill = {
            "name": d.name,
            "has_skill_md": (d / "SKILL.md").exists(),
            "has_run": (d / "run.py").exists(),
            "has_test": (d / "test.py").exists(),
        }
        skills.append(skill)
    return {"skills": skills, "total": len(skills)}


def get_alerts() -> list[dict]:
    """检查所有告警条件。"""
    alerts = []
    health = get_system_health()

    for w in health.get("warnings", []):
        alerts.append({"level": "warning", "message": w})
    for c in health.get("criticals", []):
        alerts.append({"level": "critical", "message": c})

    metrics = get_pipeline_metrics()
    error_rate = 100 - metrics.get("success_rate_pct", 100)
    if error_rate > ERROR_RATE_WARN:
        alerts.append({
            "level": "warning",
            "message": f"Error rate {error_rate:.1f}% exceeds threshold {ERROR_RATE_WARN}%",
        })

    skill_status = get_skill_status()
    for s in skill_status.get("skills", []):
        missing = []
        if not s["has_skill_md"]:
            missing.append("SKILL.md")
        if not s["has_run"]:
            missing.append("run.py")
        if missing:
            alerts.append({
                "level": "warning",
                "message": f"Skill '{s['name']}' missing: {', '.join(missing)}",
            })

    return alerts


def run_ops_check(inputs: dict | None = None) -> dict[str, Any]:
    """
    Pipeline handler: 执行运行监控检查。
    inputs 可选: {"record_run": {"phase": ..., "duration_ms": ..., "success": ...}}
    """
    inputs = inputs or {}

    if "record_run" in inputs:
        rr = inputs["record_run"]
        record_pipeline_run(rr.get("phase", "unknown"), rr.get("duration_ms", 0), rr.get("success", True))

    return {
        "status": "ok",
        "phase": "ops_monitor",
        "system_health": get_system_health(),
        "pipeline_metrics": get_pipeline_metrics(),
        "skill_status": get_skill_status(),
        "alerts": get_alerts(),
    }
