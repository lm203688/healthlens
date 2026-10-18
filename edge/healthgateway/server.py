"""网关本地只读 HTTP 口

只开 GET，且只回 JSON：
- GET /health        存活探针
- GET /status        网关 + 信号源状态
- GET /metrics?day=  当天（或指定日）聚合指标

为什么还要这个口：让用户在手机浏览器/断网时能看见盒子到底采到没有，
以及让云端 connector 用 `边缘 -> 本地 -> 云端` 的方式旁路取证（不依赖推送）。
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from command_whitelist import _read_state
from signal_source import MuseLslSource


class _Handler(BaseHTTPRequestHandler):
    server_version = "HealthLensGateway/0.1"

    def _send_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        try:
            if route == "/health":
                self._send_json({"ok": True, "service": "healthgateway"})
            elif route == "/status":
                self._send_json({"ok": True, **_read_state(self.server.data_dir)})
            elif route == "/metrics":
                from datetime import date

                day = (query.get("day") or [date.today().isoformat()])[0]
                payload = self.server.metrics_provider(day)
                self._send_json({"ok": True, "day": day, **payload})
            elif route == "/commands":
                from command_whitelist import allowed_commands

                self._send_json({"ok": True, "commands": allowed_commands()})
            else:
                self._send_json({"ok": False, "error": "not found"}, code=404)
        except Exception as exc:  # 本地口，任何异常都转成 JSON 而不是 502 裸栈
            self._send_json({"ok": False, "error": repr(exc)}, code=500)

    def log_message(self, fmt, *args):  # 静音默认 stderr 打点，改由 log.tail 统一读
        return


def start_server(host: str, port: int, data_dir: str, metrics_provider) -> ThreadingHTTPServer:
    from pathlib import Path

    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.data_dir = Path(data_dir)
    httpd.metrics_provider = metrics_provider
    httpd.serve_forever()


def probe_source_state(source) -> dict:
    """给 /status 用的信号源自检（不阻塞超过 2 秒）"""
    if not isinstance(source, MuseLslSource):
        return {"kind": getattr(source, "kind", "unknown"), "available": bool(getattr(source, "available", True))}
    try:
        return {"kind": source.kind, "available": source.available}
    except Exception:
        return {"kind": source.kind, "available": False}
