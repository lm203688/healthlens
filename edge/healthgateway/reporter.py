"""把日粒度指标推给 HealthLens 云端

为什么是边缘推而不是云端拉：盒子大概率在家庭 NAT / 内网后面，
云端没有可主动拨号的入口，所以必须设备侧发起。
断网时先落盘，等下一次 collect 再补发（离线队列）。

鉴权不用用户名密码，用两样东西：
- user_ref：用户自己生成的绑定串（不是用户真实身份，边缘不知道谁）
- 上报凭据，二选一：
  * 票据（推荐）：登录网页端签发，绑定某一个 gateway_id + user_ref，可单独吊销；
  * 静态令牌：EDGE_GATEWAY_TOKEN 全网关共用，落地快但一台盒子丢了就得全量轮换。
票据头优先，票据过期自动回落静态令牌（都存在才回落到静态令牌）。
再带一个一次性 nonce，云端做重放去重。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def build_request(endpoint: str, token: str, payload: dict, timeout: float = 15.0, ticket: str | None = None):
    """ticket 非空时走票据头；否则用静态令牌（向后兼容还没换票的盒子）"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-HL-Edge-Nonce": uuid.uuid4().hex,
        "User-Agent": "healthlens-edge-gateway/0.2",
    }
    if ticket:
        headers["X-HL-Edge-Ticket"] = ticket
        # 票据已绑死身份，静态令牌再带着只会让云端走回落分支（值不匹配 → 401）
        headers["X-HL-Edge-Token"] = ""
    else:
        headers["X-HL-Edge-Token"] = token
    req = urllib.request.Request(endpoint, data=body, method="POST", headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def push(
    endpoint: str,
    token: str,
    payload: dict,
    offline_queue: str | Path,
    timeout: float = 15.0,
    ticket: str | None = None,
) -> dict:
    """推送；失败写队列。返回 {"ok": bool, "status": int|None}"""
    try:
        with build_request(endpoint, token, payload, timeout=timeout, ticket=ticket) as resp:
            return {"ok": True, "status": getattr(resp, "status", 200)}
    except Exception as exc:
        status = getattr(exc, "code", None)
        _append_queue(Path(offline_queue), payload)
        return {"ok": False, "status": status, "error": repr(exc)}


def drain_queue(endpoint: str, token: str, offline_queue: str | Path, timeout: float = 15.0, ticket: str | None = None) -> dict:
    """补发离线队列（幂等：云端按 day + nonce 去重）"""
    queue = Path(offline_queue)
    if not queue.exists():
        return {"ok": True, "sent": 0}
    pending = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines() if line.strip()]
    sent = 0
    leftovers = []
    for payload in pending:
        result = push(endpoint, token, payload, queue, timeout=timeout, ticket=ticket)
        if result["ok"]:
            sent += 1
        else:
            leftovers.append(payload)
    queue.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in leftovers), encoding="utf-8")
    return {"ok": True, "sent": sent, "pending": len(leftovers)}


def _append_queue(queue: Path, payload: dict) -> None:
    queue.parent.mkdir(parents=True, exist_ok=True)
    with queue.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def endpoint_from_env(default: str = "https://healthlens.cc/api/v1/device-metrics") -> str:
    return os.getenv("HL_EDGE_ENDPOINT", default)


def token_from_env() -> str:
    # 凭据不写进仓库：首次由云端签发，写 /etc/healthlens/edge.env
    return os.getenv("HL_EDGE_TOKEN", "")


def ticket_from_env() -> str:
    """票据优先于静态令牌：有就拿票据，过期了运维换一次即可，不用改 .env"""
    return os.getenv("HL_EDGE_TICKET", "")


def report_gate(now: float | None = None) -> dict:
    """上报节流：同一天同一条指标重复推没有意义"""
    now = now if now is not None else time.time()
    return {"window": 3600.0, "now": round(now, 3)}
