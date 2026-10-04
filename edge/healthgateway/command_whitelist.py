"""只读命令白名单

参考 Meta `linux/src/musegadget/executor.py` 的 COMMAND_SPECS 结构，
但把它「给 agent 完整 shell 权限」那一条整个删掉：
我们这台盒子贴着用户的卧室，给它开 shell 等于给远端开门。
"""
from __future__ import annotations

import os
from pathlib import Path

GATEWAY_LOG = "gateway.log"
MAX_LOG_LINES = 50

COMMAND_SPECS: dict[str, dict] = {
    "status": {
        "readonly": True,
        "desc": "网关与信号源状态",
        "args": {},
    },
    "device.list": {
        "readonly": True,
        "desc": "列出已连接的信号源",
        "args": {},
    },
    "metrics.query": {
        "readonly": True,
        "desc": "查询某天聚合出的健康指标",
        "args": {"day": str, "key": str},
    },
    "pair.status": {
        "readonly": True,
        "desc": "配对与最近上报状态",
        "args": {},
    },
    "log.tail": {
        "readonly": True,
        "desc": "只回读网关自己的日志尾部",
        "args": {"lines": int},
    },
}


def allowed_commands() -> list[str]:
    return sorted(COMMAND_SPECS)


def dispatch(name: str, data_dir: str | Path = ".", **kwargs) -> dict:
    """执行命令，只返回 JSON-safe 结果；未知命令返回 error 而不抛异常"""
    spec = COMMAND_SPECS.get(name)
    if spec is None:
        return {"ok": False, "error": f"未知命令：{name}", "allowed": allowed_commands()}
    data_dir = Path(data_dir)

    if name == "status":
        return {"ok": True, "command": name, "result": _read_state(data_dir)}
    if name == "device.list":
        return {"ok": True, "command": name, "result": {"sources": _read_state(data_dir).get("sources", {})}}
    if name == "metrics.query":
        day, key = kwargs.get("day"), kwargs.get("key")
        return {"ok": True, "command": name, "result": _query_metrics(data_dir, day, key)}
    if name == "pair.status":
        return {"ok": True, "command": name, "result": _read_state(data_dir).get("last_report", {})}
    if name == "log.tail":
        lines = max(1, min(int(kwargs.get("lines", 20)), MAX_LOG_LINES))
        return {"ok": True, "command": name, "result": {"lines": _tail_log(data_dir, lines)}}
    return {"ok": False, "error": "命令未实现"}


def _state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def _read_state(data_dir: Path) -> dict:
    path = _state_path(data_dir)
    if not path.exists():
        return {"data_dir": str(data_dir), "sources": {}, "last_report": {}}
    return dict(path.read_text(encoding="utf-8"))


def _write_state(data_dir: Path, state: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    _state_path(data_dir).write_text(_json(state), encoding="utf-8")


def _json(payload) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _query_metrics(data_dir: Path, day: str | None, key: str | None) -> dict:
    day = day or _today()
    path = data_dir / "metrics" / f"{day}.json"
    if not path.exists():
        return {"day": day, "found": False}
    payload = path.read_text(encoding="utf-8")
    import json

    data = json.loads(payload)
    if key:
        data = [m for m in data.get("metrics", []) if m.get("key") == key]
    return {"day": day, "found": True, "data": data}


def _today() -> str:
    from datetime import date

    return date.today().isoformat()


def _tail_log(data_dir: Path, lines: int) -> list[str]:
    """只读网关自己的日志文件，拒绝任意路径（防目录穿越）"""
    base = data_dir.resolve()
    candidate = (data_dir / GATEWAY_LOG).resolve()
    if base not in candidate.parents and candidate != base:
        return ["日志路径越权"]
    if not candidate.exists():
        return []
    with candidate.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.readlines()[-lines:]


__all__ = ["COMMAND_SPECS", "allowed_commands", "dispatch", "_write_state", "_read_state"]
