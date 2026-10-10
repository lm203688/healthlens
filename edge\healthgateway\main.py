"""网关 CLI：collect / serve / report / status

用法（树莓派上常驻）：
    python -m healthgateway.main collect --seconds 60 --loop
    python -m healthgateway.main serve --port 8421
    python -m healthgateway.main report

无硬件自测：
    python -m healthgateway.main collect --kind synthetic --seconds 8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate import (  # noqa: E402
    WINDOW_SECONDS,
    MetricWindow,
    build_payload,
    compute_band_metrics,
)
from command_whitelist import dispatch  # noqa: E402
from pulse_source import (
    WINDOW_SECONDS as PULSE_WINDOW,
)
from pulse_source import (  # noqa: E402
    PulsePpgSource,
    PulseSerialSource,
)
from reporter import (  # noqa: E402
    drain_queue,
    endpoint_from_env,
    push,
    ticket_from_env,
    token_from_env,
)
from signal_source import build_source  # noqa: E402

DEFAULT_DATA_DIR = os.getenv("HL_EDGE_DATA_DIR", "./data")
DEFAULT_GATEWAY_ID = os.getenv("HL_EDGE_GATEWAY_ID", "hlgw-local")
DEFAULT_USER_REF = os.getenv("HL_EDGE_USER_REF", "local")
DEVICE_LABEL = {
    "muse_lsl": "InteraXon Muse (muse-lsl)",
    "replay": "replay file",
    "synthetic": "synthetic (no device)",
}


def _day() -> str:
    return date.today().isoformat()


def _metrics_dir(data_dir: Path) -> Path:
    path = data_dir / "metrics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_metrics(data_dir: Path, day: str, payload: dict) -> Path:
    path = _metrics_dir(data_dir) / f"{day}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_metrics(data_dir: Path, day: str) -> dict:
    path = _metrics_dir(data_dir) / f"{day}.json"
    if not path.exists():
        return {"metrics": []}
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_collect(args) -> int:
    if args.kind == "pulse":
        return _collect_pulse(args)
    source = build_source({"kind": args.kind, "path": args.path,
                           "sample_rate": args.sample_rate, "noise": args.noise})
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    window = MetricWindow(window_seconds=WINDOW_SECONDS)

    frames = max(1, int(round(args.seconds / WINDOW_SECONDS)))
    for _ in range(frames):
        frame = source.read(seconds=WINDOW_SECONDS)
        window.push(compute_band_metrics(frame, window=WINDOW_SECONDS))

    metrics = window.flush()
    day = args.day or _day()
    payload = build_payload(
        day=day,
        gateway_id=args.gateway_id,
        user_ref=args.user_ref,
        metrics=metrics,
        device={"type": args.kind, "label": DEVICE_LABEL.get(args.kind, args.kind)},
    )
    path = _write_metrics(data_dir, day, payload)
    # state.json 只存纯状态体（_read_state 直接用 json.load 读进 dict），
    # 命令层的 {"ok", "command", "result"} 包装只在 dispatch 返回时加。
    state = dispatch("status", data_dir=data_dir).get("result", {}) or {}
    state.update({
        "gateway_id": args.gateway_id,
        "user_ref": args.user_ref,
    })
    state["last_collect"] = {
        "day": day,
        "frames": metrics.get("frames", 0),
        "band_relative": metrics.get("band_relative"),
        "alpha_asymmetry": metrics.get("alpha_asymmetry"),
        "saved_at": datetime.now(UTC).isoformat(),
        "sources": {args.kind: True},
    }
    (data_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")  # noqa: E501
    print(json.dumps({"ok": True, "saved": str(path), **metrics}, ensure_ascii=False, indent=2))

    if args.loop:
        time.sleep(args.interval)
    return 0


def _collect_pulse(args) -> int:
    """号脉采集：每窗取一次 hl.pulse.* 特征，多窗平均后上送。

    源优先级：--serial-file（回放固件输出）> --port（真实串口读固件）> --profile（合成波形）。
    """
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    if getattr(args, "serial_file", None):
        src = PulseSerialSource(file=args.serial_file, sample_rate=args.sample_rate)
    elif getattr(args, "port", None):
        src = PulseSerialSource(port=args.port, baudrate=115200, sample_rate=args.sample_rate)
    else:
        src = PulsePpgSource(profile=getattr(args, "profile", "normal") or "normal",
                             sample_rate=args.sample_rate, noise=args.noise, seed=None)
    frames = max(1, int(round(args.seconds / PULSE_WINDOW)))
    agg: dict[str, list[float]] = {}
    for _ in range(frames):
        feats = src.read(seconds=PULSE_WINDOW)
        for k, v in feats.items():
            if isinstance(v, (int, float)):
                agg.setdefault(k, []).append(v)
    metrics = []
    for k, vals in agg.items():
        metrics.append({
            "key": k,
            "value": round(sum(vals) / len(vals), 4),
            "unit": "ratio" if ("ratio" in k or k.endswith("_bpm") or "slope" in k or "index" in k or "regularity" in k) else None,
            "evidence": "edge-derived",
            "sample_count": len(vals),
        })
    # 注：depth / pause_pattern 为字符串，不满足接收口 value:float 约束，
    # V0 单点常规定律不强制上送；云端引擎对缺失项取默认值（none/""）。
    day = args.day or _day()
    payload = build_payload(
        day=day,
        gateway_id=args.gateway_id,
        user_ref=args.user_ref,
        metrics={"metrics": metrics, "frames": frames},
        device={"type": "pulse", "label": "HealthLens 号脉终端 (PPG)"},
    )
    path = _write_metrics(data_dir, day, payload)
    state = dispatch("status", data_dir=data_dir).get("result", {}) or {}
    state.update({"gateway_id": args.gateway_id, "user_ref": args.user_ref})
    state["last_collect"] = {
        "day": day,
        "frames": frames,
        "pulse_features": {m["key"]: m["value"] for m in metrics if isinstance(m["value"], (int, float))},
        "saved_at": datetime.now(UTC).isoformat(),
        "sources": {"pulse": True},
    }
    (data_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "saved": str(path), "metrics_count": len(metrics)}, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args) -> int:
    import server as gateway_server

    data_dir = Path(args.data_dir)

    def provider(day: str) -> dict:
        return _load_metrics(data_dir, day)

    data_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"ok": True, "serving": f"{args.host}:{args.port}", "data_dir": str(data_dir)}))
    gateway_server.start_server(args.host, args.port, str(data_dir), provider)
    return 0


def cmd_report(args) -> int:
    data_dir = Path(args.data_dir)
    queue = data_dir / "offline.jsonl"
    endpoint = args.endpoint or endpoint_from_env()
    token = args.token or token_from_env()
    ticket = ticket_from_env()

    if not token and not ticket:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "缺上报凭据：设 HL_EDGE_TICKET（推荐，网页端签发）或 HL_EDGE_TOKEN（静态令牌）",
                    "endpoint": endpoint,
                }
            )
        )
        return 2

    day = args.day or _day()
    payload = _load_metrics(data_dir, day)
    if not payload.get("metrics"):
        print(json.dumps({"ok": False, "error": f"{day} 无聚合指标，先跑 collect"}))
        return 3

    result = push(endpoint, token, payload, queue, ticket=ticket)
    if result["ok"]:
        result["sent_day"] = day
    else:
        result["queued"] = str(queue)
    result["drained"] = drain_queue(endpoint, token, queue, ticket=ticket)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_status(args) -> int:
    print(json.dumps(dispatch("status", data_dir=Path(args.data_dir)), ensure_ascii=False, indent=2))
    return 0


def cmd_commands(args) -> int:
    print(json.dumps(dispatch("log.tail", data_dir=Path(args.data_dir), lines=args.lines), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="healthgateway", description="HealthLens 边缘网关")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _with_data_dir(sub_parser):
        # 子命令各自带 --data-dir：argparse 不会把父级选项带进子命令，
        # 也不存在“父级在后”这种位置，所以每个子命令都要自己认这个参数。
        sub_parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
        return sub_parser

    collect = sub.add_parser("collect")
    collect.add_argument("--kind", default="synthetic", choices=["synthetic", "replay", "muse_lsl", "pulse"])
    collect.add_argument("--profile", default="normal",
                        help="pulse 源波形形态: normal/xian/shu/chi/ji/hong/se/hua")
    collect.add_argument("--port", default=None,
                        help="号脉固件串口(COM3 / /dev/ttyUSB0)；指定则读真实硬件而非合成")
    collect.add_argument("--serial-file", default=None,
                        help="号脉固件输出回放文件(JSONL)，无硬件验证整条链路用")
    collect.add_argument("--path")
    collect.add_argument("--sample-rate", type=int, default=256)
    collect.add_argument("--noise", type=float, default=0.1)
    collect.add_argument("--seconds", type=float, default=60.0)
    collect.add_argument("--interval", type=float, default=60.0)
    collect.add_argument("--loop", action="store_true")
    collect.add_argument("--day")
    collect.add_argument("--gateway-id", default=DEFAULT_GATEWAY_ID)
    collect.add_argument("--user-ref", default=DEFAULT_USER_REF)
    collect = _with_data_dir(collect)
    collect.set_defaults(func=cmd_collect)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8421)
    serve = _with_data_dir(serve)
    serve.set_defaults(func=cmd_serve)

    report = sub.add_parser("report")
    report.add_argument("--endpoint", default=None)
    report.add_argument("--token", default=None)
    report.add_argument("--day")
    report = _with_data_dir(report)
    report.set_defaults(func=cmd_report)

    status = sub.add_parser("status")
    status = _with_data_dir(status)
    status.set_defaults(func=cmd_status)

    logs = sub.add_parser("log")
    logs.add_argument("--lines", type=int, default=20)
    logs = _with_data_dir(logs)
    logs.set_defaults(func=cmd_commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
