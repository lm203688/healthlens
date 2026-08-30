"""
阶段8：运维管理 — 数据库初始化 / 备份 / watchdog 巡检

真实执行各运维组件并汇总结果。

此前此文件仅做 path.exists() 检查便上报 "available"，3 个运维组件
（db_setup / backup_db / watchdog，共 900+ 行真实实现）从未被调用，却恒定
返回 0，形成"虚假成功"。现改为 subprocess 真实执行，并将失败反映到退出码。

可通过 --params 传入：
  {"modules": ["watchdog"], "timeout": 120}   # 只跑指定组件 / 调整超时
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

COMPONENTS = [
    ("db_setup", "db_setup.py"),
    ("backup", "backup_db.py"),
    ("watchdog", "watchdog.py"),
]


def _load_params() -> dict:
    if "--params" in sys.argv:
        idx = sys.argv.index("--params")
        try:
            return json.loads(sys.argv[idx + 1])
        except Exception:
            return {}
    return {}


def main() -> int:
    params = _load_params()
    only = params.get("modules")
    timeout = int(params.get("timeout", 180))

    results = []
    for name, script in COMPONENTS:
        if only and name not in only:
            results.append({"component": name, "script": script, "status": "skipped"})
            continue

        path = HERE / script
        if not path.exists():
            results.append({"component": name, "script": script, "status": "missing"})
            continue

        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(HERE),
            )
            results.append({
                "component": name,
                "script": script,
                "status": "ok" if proc.returncode == 0 else "error",
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-2000:],
                "stderr": (proc.stderr or "")[-1000:],
            })
        except subprocess.TimeoutExpired:
            results.append({
                "component": name,
                "script": script,
                "status": "timeout",
                "timeout": timeout,
            })
        except Exception as exc:
            results.append({
                "component": name,
                "script": script,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    executed = [r for r in results if r["status"] in ("ok", "error", "timeout")]
    failed = [r for r in executed if r["status"] != "ok"]

    output = {
        "phase": 8,
        "components": results,
        "summary": {
            "total": len(results),
            "executed": len(executed),
            "ok": len(executed) - len(failed),
            "failed": len(failed),
            "failed_components": [r["component"] for r in failed],
        },
        "params": params,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    # 有失败则返回非 0 —— 此前恒定返回 0，导致失败永远不可见
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
