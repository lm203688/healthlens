"""
HealthLens 自动化管线

包装 auto-pipeline/scripts/phase_1~8 的独立脚本，
提供统一 API 接口：run_phase(phase_id, **params) / run_all()
支持 dry_run 模式和状态查询。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AUTO_PIPELINE_DIR = ROOT / "auto-pipeline" / "scripts"

PHASES = {
    1: "phase_1_collect",
    2: "phase_2_analyze",
    3: "phase_3_decide",
    4: "phase_4_develop",
    5: "phase_5_test",
    6: "phase_6_deploy",
    7: "phase_7_feedback",
    8: "phase_8_ops",
}

PHASE_DESCRIPTIONS = {
    1: "情报收集：GitHub Trending / arXiv / PubMed / 竞品",
    2: "多源分析：信号聚类 / 主题建模 / 知识图谱",
    3: "决策矩阵：SWOT / 优先级排序 / 风险评估",
    4: "迭代开发：需求生成 / 代码骨架 / 设计文档",
    5: "测试验证：pytest / ruff / 覆盖率 / 安全扫描",
    6: "构建部署：npm build / Docker / CF Pages 部署",
    7: "反馈闭环：财务 / 用户转化 / 推广 / 数据资产",
    8: "运维管理：数据库备份 / watchdog / 告警",
}


def list_phases() -> list[dict]:
    """返回所有可用的管线阶段列表。"""
    result = []
    for pid, dirname in PHASES.items():
        phase_dir = AUTO_PIPELINE_DIR / dirname
        has_run = (phase_dir / "run.py").exists() if phase_dir.exists() else False
        result.append({
            "phase": pid,
            "name": dirname,
            "description": PHASE_DESCRIPTIONS.get(pid, ""),
            "has_run": has_run,
            "path": str(phase_dir),
        })
    return result


def preflight(phase_id: int) -> dict:
    """静态预检：在不执行脚本的前提下验证其可运行性。

    检查项：
      1. 阶段目录是否存在
      2. run.py 是否存在
      3. run.py 是否通过语法编译（捕捉语法错误，不执行代码）
      4. 阶段目录下其他 .py 是否语法正常

    返回 {"ok": bool, "checks": [...], "errors": [...]}
    """
    checks: list[dict] = []
    errors: list[str] = []

    dirname = PHASES.get(phase_id)
    if dirname is None:
        return {"ok": False, "checks": [], "errors": [f"未知阶段: {phase_id}"]}

    phase_dir = AUTO_PIPELINE_DIR / dirname
    dir_exists = phase_dir.is_dir()
    checks.append({"item": "phase_dir", "target": str(phase_dir), "ok": dir_exists})
    if not dir_exists:
        errors.append(f"阶段目录不存在: {phase_dir}")
        return {"ok": False, "checks": checks, "errors": errors}

    run_script = phase_dir / "run.py"
    run_exists = run_script.exists()
    checks.append({"item": "run_py", "target": str(run_script), "ok": run_exists})
    if not run_exists:
        errors.append(f"run.py 不存在: {run_script}")
        return {"ok": False, "checks": checks, "errors": errors}

    # 语法编译检查（只编译，不执行，无副作用）
    import py_compile

    scripts = sorted(phase_dir.glob("*.py"))
    for script in scripts:
        try:
            py_compile.compile(str(script), cfile=None, doraise=True)
            checks.append({"item": "syntax", "target": script.name, "ok": True})
        except Exception as exc:
            checks.append({"item": "syntax", "target": script.name, "ok": False})
            errors.append(f"{script.name} 语法错误: {type(exc).__name__}: {exc}")

    return {"ok": not errors, "checks": checks, "errors": errors}


# 阶段输出保留上限。此前固定截断到最后 500 字符，会截碎结构化 JSON 报告，
# 导致上层 json.loads 失败。现按此上限保留（足以容纳完整报告），超出才截断。
OUTPUT_LIMIT = 50_000


def _truncate_output(text: str | None) -> str:
    """保留输出，仅在超过上限时截断并标注。"""
    if not text:
        return ""
    if len(text) <= OUTPUT_LIMIT:
        return text
    dropped = len(text) - OUTPUT_LIMIT
    return f"{text[:OUTPUT_LIMIT]}\n...[截断 {dropped} 字符，超过上限 {OUTPUT_LIMIT}]"


def run_phase(phase_id: int, dry_run: bool = False, **params: Any) -> dict:
    """
    执行指定阶段。

    dry_run=True 时只打印将执行什么，不实际运行。
    返回：{"status": "ok"/"skipped"/"error", "phase": id, "output": ...}
    """
    if phase_id not in PHASES:
        return {"status": "error", "phase": phase_id, "error": f"未知阶段: {phase_id}"}

    dirname = PHASES[phase_id]
    phase_dir = AUTO_PIPELINE_DIR / dirname
    run_script = phase_dir / "run.py"

    if not run_script.exists():
        return {"status": "error", "phase": phase_id, "error": "run.py 不存在"}

    if dry_run:
        # 静态预检：真正验证脚本可运行性（此前仅返回 skipped，无法用于健康巡检）
        check = preflight(phase_id)
        return {
            "status": "ok" if check["ok"] else "error",
            "phase": phase_id,
            "dry_run": True,
            "description": PHASE_DESCRIPTIONS.get(phase_id, ""),
            "script": str(run_script),
            "params": params,
            "preflight": check,
            "errors": check["errors"],
            "note": "dry_run 静态预检完成，未实际执行",
        }

    # 准备状态目录
    state_dir = ROOT / ".pipeline_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [sys.executable, str(run_script), "--params", json.dumps(params, ensure_ascii=False)],
            capture_output=True,
            text=True,
            cwd=str(phase_dir),
            timeout=300,
            env={**__import__("os").environ, "HEALTHLENS_ROOT": str(ROOT)},
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "phase": phase_id,
            "returncode": result.returncode,
            "stdout": _truncate_output(result.stdout),
            "stderr": _truncate_output(result.stderr),
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "phase": phase_id, "error": "执行超时（300s）"}
    except Exception as exc:
        return {"status": "error", "phase": phase_id, "error": str(exc)}


def run_all(dry_run: bool = False) -> list[dict]:
    """依次执行所有 8 个阶段。"""
    return [run_phase(pid, dry_run=dry_run) for pid in sorted(PHASES)]


def get_pipeline_status() -> dict:
    """返回管线运行状态。"""
    state_dir = ROOT / ".pipeline_state"
    if not state_dir.exists():
        return {"status": "idle", "phases": [], "note": "从未执行"}

    phases = []
    for f in sorted(state_dir.iterdir()):
        if f.suffix == ".json":
            try:
                phases.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                phases.append({"file": f.name, "error": "解析失败"})
    return {"status": "done" if phases else "idle", "phases": phases}
