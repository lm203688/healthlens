"""统一告警模块（2026-08-04 新增）

背景
----
在此之前整个系统没有任何告警能力。2026-08-03 的实跑记录是这样的：

    [03:01:31] 数据库查询失败: 远程计算机拒绝网络连接
    [03:01:31]   ✅ E: E.资金闭环 - 成功
    [03:01:36] F线运维检查完成: 端点 0/4正常
    [03:01:36]   ✅ F: F.项目运维闭环 - 成功
    [03:01:36] 全部闭环执行结束: 全部成功

站点全挂、数据库拒连，系统报「全部成功」。这比没有监控更危险——
它提供的是虚假的安全感。本模块是把 fail-open 改成 fail-loud 的基础设施。

设计原则
--------
1. **绝不因为告警发送失败而让业务崩溃**：所有通道单独 try/except，
   一个通道挂了不影响其他通道，最后至少保证本地文件通道成功。
2. **本地文件通道永远启用**：webhook 可能没配、网络可能不通，
   但本地落盘几乎不会失败，它是最后的证据留存。
3. **去重与冷却**：同一故障持续存在时不刷屏，但也不能彻底静默——
   采用「首次立即告警 + 冷却期内静默 + 冷却期满重新告警」。
4. **恢复通知**：故障消失时主动发 resolved，否则人永远不知道
   问题是不是已经好了。

通道优先级：本地文件（必选）→ Webhook（可选）→ 桌面通知（可选）
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ALERT_DIR = BASE_DIR / "alerts"
STATE_FILE = ALERT_DIR / "alert_state.json"
ACTIVE_MD = ALERT_DIR / "ACTIVE_ALERTS.md"

LEVEL_INFO = "INFO"
LEVEL_WARN = "WARN"
LEVEL_CRITICAL = "CRITICAL"

_LEVEL_ICON = {LEVEL_INFO: "ℹ️", LEVEL_WARN: "⚠️", LEVEL_CRITICAL: "🔴"}
_LEVEL_RANK = {LEVEL_INFO: 0, LEVEL_WARN: 1, LEVEL_CRITICAL: 2}

# 同一 dedup_key 的重复告警冷却时间（秒）
DEFAULT_COOLDOWN = 3600 * 4  # 4 小时

# 陈旧告警过期阈值（天）。活跃告警若 last_seen 距今超过该天数且期间未再出现，
# 会在下次被读取时自动从活跃清单移除。取值权衡：太短会误杀真实持续中的故障，
# 太长则让早已失效的告警长期阻塞流水线。14 天 ≈ 2 周，配合每 2 小时的流水线
# 与每 3 小时的看门狗，足以覆盖间歇性复发；新出现的 CRITICAL 仍会立即阻断。
DEFAULT_STALE_DAYS = 14

# 已提示过「缺少环境变量」的变量名集合（每进程去重，避免告警风暴）
_MISSING_SECRET_WARNED: set = set()

# 本机加载凭据的推荐方式（写进提示文案，避免每次都要重新翻配置注释）
_ENV_HINT = ("在本机 source .workbuddy/cache/env.sh（内含 export SERVERCHAN_SENDKEY=xxx）"
             "，或直接在当前 shell 执行 export SERVERCHAN_SENDKEY=<你的SendKey>")


def env_hint() -> str:
    return _ENV_HINT


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def _load_config() -> dict:
    try:
        with open(BASE_DIR / "config.json", encoding="utf-8") as f:
            return json.load(f).get("alerting", {})
    except Exception:
        return {}


# --------------------------------------------------------------------------
# 告警状态（去重 / 冷却 / 活跃列表）
# --------------------------------------------------------------------------
def _load_alert_state() -> dict:
    if not STATE_FILE.exists():
        return {"active": {}, "history_count": 0}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": {}, "history_count": 0}


def _save_alert_state(state: dict) -> None:
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


# --------------------------------------------------------------------------
# 通道 1：本地文件（必选，永不禁用）
# --------------------------------------------------------------------------
def _channel_file(payload: dict) -> bool:
    try:
        ALERT_DIR.mkdir(parents=True, exist_ok=True)
        # 追加到当日 jsonl，便于后续统计
        daily = ALERT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(daily, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[alerting] 文件通道失败: {e}", file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# 通道 2：Webhook（可选，支持企业微信 / 钉钉 / Server酱 / 通用 JSON）
# --------------------------------------------------------------------------
def _build_webhook_body(kind: str, payload: dict) -> dict:
    icon = _LEVEL_ICON.get(payload["level"], "")
    text = (
        f"{icon} [HealthLens/{payload['level']}] {payload['title']}\n"
        f"{payload['message']}\n"
        f"时间: {payload['timestamp']}"
    )
    if kind in ("wecom", "dingtalk"):  # 企业微信 / 钉钉机器人
        return {"msgtype": "text", "text": {"content": text}}
    if kind == "serverchan":  # Server酱
        return {"title": f"[{payload['level']}] {payload['title']}"[:100],
                "desp": payload["message"]}
    return payload  # generic：原样投递


def _build_webhook_request(kind: str, payload: dict) -> tuple[bytes, str]:
    """返回 (body_bytes, content_type)。

    Server酱 API 只接受表单编码（application/x-www-form-urlencoded）；发
    application/json 时 title/desp 会被丢弃，即便 SendKey 正确也推不出消息。
    企业微信 / 钉钉 / 通用通道才是 JSON。此前所有通道一律发 JSON，Server酱
    通道因此必然静默失败——这是「配了告警却从没收到」这类问题的隐性根因。
    """
    body = _build_webhook_body(kind, payload)
    if kind == "serverchan":
        import urllib.parse
        return (urllib.parse.urlencode(body).encode("utf-8"),
                "application/x-www-form-urlencoded")
    return json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json"


def _warn_missing_secret(names: list, kind: str) -> None:
    """凭据缺失提醒：每个变量名每进程只提示一次，避免告警风暴。

    历史上 CI 里 SERVERCHAN_SENDKEY 未配置，webhook 通道每次告警都发 403，
    日志噪音反而掩盖了真实问题；这里改成一次性提示 + 明确的修复路径。
    """
    global _MISSING_SECRET_WARNED
    for n in names:
        if n in _MISSING_SECRET_WARNED:
            continue
        _MISSING_SECRET_WARNED.add(n)
        print(
            f"[alerting] webhook({kind}) 通道跳过：缺少环境变量 {n}\n"
            f"            修复方式二选一 ——\n"
            f"            1) 本机跑流水线：{env_hint()}\n"
            f"            2) GitHub Actions：仓库 Settings → Secrets and variables → Actions\n"
            f"               → New repository secret，名称 {n}，值为 SendKey 原文。",
            file=sys.stderr,
        )


def _channel_webhook(payload: dict, cfg: dict) -> bool:
    hooks = cfg.get("webhooks", [])
    if not hooks:
        return False

    try:
        import urllib.error
        import urllib.request
    except Exception:
        return False

    any_ok = False
    for hook in hooks:
        if not hook.get("enabled", True):
            continue
        url = hook.get("url", "").strip()
        # 支持 ${ENV_VAR} 展开：真实密钥（如 Server酱 SendKey）只放本机环境变量或
        # .workbuddy/cache/env.sh，config.json 里留占位符即可安全入库。
        # 本仓库是公开仓库，历史上 SendKey 曾明文写在 config.json，2026-08-29 已改为展开式。
        #
        # 注意：展开后必须校验「被替换的变量本身非空」——若环境变量未设置，
        # re.sub 会把 ${SERVERCHAN_SENDKEY} 替换成空串，url 变成
        # "https://sctapi.ftqq.com/.send"：非空、也不含 "${"，
        # 旧守卫（if not url or "${" in url）完全拦不住，于是每次告警都往
        # 坏 URL 发 POST，CI 日志里稳定刷 "webhook(serverchan) 失败: HTTP Error 403"。
        # 2026-09-15 修正：改用「是否发生空值展开」判断，缺失凭据时静默跳过。
        if "${" in url:
            import re
            missing = []

            def _expand(m: "re.Match") -> str:
                val = os.environ.get(m.group(1), "")
                if not val:
                    missing.append(m.group(1))
                return val

            url = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _expand, url)
            if not url or "${" in url or missing:
                if missing:
                    _warn_missing_secret(missing, hook.get("kind", "generic"))
                continue
        if not url or url.startswith("<"):  # 占位符未替换
            continue
        # 只在告警级别 >= 该通道阈值时才发
        min_level = hook.get("min_level", LEVEL_WARN)
        if _LEVEL_RANK.get(payload["level"], 0) < _LEVEL_RANK.get(min_level, 1):
            continue

        body, ctype = _build_webhook_request(hook.get("kind", "generic"), payload)
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": ctype},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    any_ok = True
        except Exception as e:
            print(f"[alerting] webhook({hook.get('kind')}) 失败: {str(e)[:120]}", file=sys.stderr)
    return any_ok


# --------------------------------------------------------------------------
# 通道 3：控制台（醒目输出，便于人工跑的时候一眼看到）
# --------------------------------------------------------------------------
def _channel_console(payload: dict) -> bool:
    icon = _LEVEL_ICON.get(payload["level"], "")
    bar = "!" * 66 if payload["level"] == LEVEL_CRITICAL else "-" * 66
    print(f"\n{bar}", file=sys.stderr)
    print(f"{icon} [{payload['level']}] {payload['title']}", file=sys.stderr)
    print(f"   {payload['message']}", file=sys.stderr)
    if payload.get("context"):
        ctx = json.dumps(payload["context"], ensure_ascii=False)[:400]
        print(f"   context: {ctx}", file=sys.stderr)
    print(f"{bar}\n", file=sys.stderr)
    return True


# --------------------------------------------------------------------------
# 活跃告警清单（人类可读，一眼看清当前有什么在烧）
# --------------------------------------------------------------------------
def _rewrite_active_md(state: dict) -> None:
    try:
        ALERT_DIR.mkdir(parents=True, exist_ok=True)
        active = state.get("active", {})
        lines = [
            "# HealthLens 活跃告警",
            "",
            f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"当前活跃: **{len(active)}** 条",
            "",
        ]
        if not active:
            lines.append("当前无活跃告警。")
        else:
            crit = [(k, v) for k, v in active.items() if v.get("level") == LEVEL_CRITICAL]
            warn = [(k, v) for k, v in active.items() if v.get("level") != LEVEL_CRITICAL]
            for title, group in (("🔴 CRITICAL", crit), ("⚠️ WARN", warn)):
                if not group:
                    continue
                lines += [f"## {title}", "", "| 告警 | 首次出现 | 最近一次 | 次数 |", "|---|---|---|---|"]
                for key, item in sorted(group, key=lambda x: x[1].get("first_seen", "")):
                    lines.append(
                        f"| {item.get('title', key)} | {item.get('first_seen', '')[:19]} "
                        f"| {item.get('last_seen', '')[:19]} | {item.get('count', 1)} |"
                    )
                lines.append("")
        with open(ACTIVE_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        print(f"[alerting] 活跃清单写入失败: {e}", file=sys.stderr)


# --------------------------------------------------------------------------
# 对外主接口
# --------------------------------------------------------------------------
def send_alert(level, title, message, context=None, dedup_key=None, cooldown=None):
    """发送告警。

    Args:
        level: LEVEL_INFO / LEVEL_WARN / LEVEL_CRITICAL
        title: 简短标题，用于通知栏
        message: 详细说明，应包含「发生了什么 + 可能原因 + 建议动作」
        context: dict，结构化上下文（会写入本地记录）
        dedup_key: 去重键。相同键在冷却期内只发一次。默认用 title。
        cooldown: 冷却秒数，默认 4 小时。

    Returns:
        dict: {"sent": bool, "suppressed": bool, "channels": {...}}
    """
    cfg = _load_config()
    if not cfg.get("enabled", True):
        return {"sent": False, "suppressed": True, "reason": "alerting disabled"}

    key = dedup_key or title
    cooldown = cooldown if cooldown is not None else cfg.get("cooldown_seconds", DEFAULT_COOLDOWN)
    now = time.time()
    now_iso = datetime.now().isoformat()

    state = _load_alert_state()
    active = state.setdefault("active", {})
    existing = active.get(key)

    suppressed = False
    if existing:
        existing["count"] = existing.get("count", 1) + 1
        existing["last_seen"] = now_iso
        existing["level"] = level
        existing["title"] = title
        # 冷却期内不重复推送（但仍然更新计数与活跃清单）
        if now - existing.get("last_notified_unix", 0) < cooldown:
            suppressed = True
        else:
            existing["last_notified_unix"] = now
    else:
        active[key] = {
            "title": title,
            "level": level,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "count": 1,
            "last_notified_unix": now,
        }

    payload = {
        "timestamp": now_iso,
        "level": level,
        "title": title,
        "message": message,
        "context": context or {},
        "dedup_key": key,
        "occurrence": active[key]["count"],
    }

    channels = {}
    # 文件通道始终写（即使被冷却抑制，也要留下发生过的证据）
    channels["file"] = _channel_file(payload)

    if not suppressed:
        channels["console"] = _channel_console(payload)
        channels["webhook"] = _channel_webhook(payload, cfg)

    state["history_count"] = state.get("history_count", 0) + 1
    _save_alert_state(state)
    _rewrite_active_md(state)

    return {"sent": not suppressed, "suppressed": suppressed, "channels": channels}


def resolve_alert(dedup_key, note=""):
    """标记某告警已恢复，并发送恢复通知。

    这一步很容易被忽略，但没有恢复通知的告警系统会训练人忽略告警——
    因为人无法区分「还在烧」和「已经好了但没人清理」。
    """
    state = _load_alert_state()
    active = state.setdefault("active", {})
    if dedup_key not in active:
        return {"resolved": False, "reason": "not active"}

    item = active.pop(dedup_key)
    payload = {
        "timestamp": datetime.now().isoformat(),
        "level": LEVEL_INFO,
        "title": f"已恢复: {item.get('title', dedup_key)}",
        "message": note or f"该问题已消失。累计出现 {item.get('count', 1)} 次，"
                           f"首次 {item.get('first_seen', '')[:19]}。",
        "context": {"resolved_from": item},
        "dedup_key": f"resolved:{dedup_key}",
        "occurrence": 1,
    }
    _channel_file(payload)
    _channel_console(payload)
    _channel_webhook(payload, _load_config())

    _save_alert_state(state)
    _rewrite_active_md(state)
    return {"resolved": True}


def get_active_alerts() -> dict:
    """返回当前活跃告警，供看门狗/报告使用。

    读的时候顺带做过期清理：陈旧告警若长期未再出现，会自动从活跃清单移除。
    没有这一步，一条 40 天前就该失效的 CRITICAL 会永久阻塞流水线——
    scheduler._crosscheck_health 只看活跃清单里的 CRITICAL 条数，它无法判断
    「这条告警是不是早就没人理了」。过期判据是 last_seen 距今超过阈值，
    而不是「没人调用 resolve」——后者取决于某个恰好会 resolve 它的检查是否运行。
    """
    expire_stale_alerts()
    return _load_alert_state().get("active", {})


def expire_stale_alerts(max_age_days=None) -> list:
    """自动过期陈旧告警：超过阈值天数未再出现 ⇒ 从活跃清单移除。

    为什么必须做：
      · 流水线判据是「活跃 CRITICAL 条数 > 0 即不健康」，而 resolve 只在
        某个专项检查主动调用时才发生。
      · 实测案例（2026-09-15）：ops:bad_deploy_target 于 2026-08-29 随配置修正
        实际消失，但无人 resolve，其 last_seen 停在 2026-08-28，此后 18 天里
        让整条定时流水线持续 FAILED（DEGRADED ⇒ exit 1），且「汇总与告警」步骤
        因此反复失败、每次都给同一个 Issue 追加评论。
      · 阈值 14 天足够长，不会误杀真实持续中的故障；新出现的 CRITICAL 仍会
        立即阻断，只是不会无限期地阻断。

    过期动作只写本地文件记录，不发 webhook、不打 console 告警——
    批量过期时不该制造新的噪音。过期事实本身留有可审计的痕迹。

    Returns:
        本次过期的 dedup_key 列表（可能为空）。
    """
    if max_age_days is None:
        cfg = _load_config()
        max_age_days = cfg.get("stale_days", DEFAULT_STALE_DAYS)

    state = _load_alert_state()
    active = state.setdefault("active", {})
    now = datetime.now()

    expired = []
    for key in list(active.keys()):
        item = active[key]
        stamp = item.get("last_seen") or item.get("first_seen") or ""
        if not stamp:
            # 缺时间戳的脏数据无法判断新旧，按陈旧处理，避免永久滞留
            expired.append(key)
            active.pop(key, None)
            continue
        try:
            seen = datetime.fromisoformat(stamp)
        except (ValueError, TypeError):
            expired.append(key)
            active.pop(key, None)
            continue
        age_days = (now - seen).total_seconds() / 86400.0
        if age_days <= max_age_days:
            continue
        active.pop(key, None)
        expired.append(key)
        _channel_file({
            "timestamp": now.isoformat(),
            "level": LEVEL_INFO,
            "title": f"已过期（陈旧自动清理）: {item.get('title', key)}",
            "message": (
                f"{key} 已 {age_days:.0f} 天未再出现（last_seen={stamp[:19]}，"
                f"阈值 {max_age_days} 天），从活跃清单移除。\n"
                f"累计出现 {item.get('count', 1)} 次，首次 {item.get('first_seen', '')[:19]}。\n"
                f"若该问题实际仍存在，下一次检查会重新登记；若确已修复，"
                f"这是一次补上的恢复记录。"
            ),
            "context": {"expired_from": item, "age_days": round(age_days, 1),
                        "threshold_days": max_age_days, "reason": "stale"},
            "dedup_key": f"expired:{key}",
            "occurrence": 1,
        })

    if expired:
        state["history_count"] = state.get("history_count", 0) + len(expired)
        _save_alert_state(state)
        _rewrite_active_md(state)
    return expired


def has_critical() -> bool:
    return any(v.get("level") == LEVEL_CRITICAL for v in get_active_alerts().values())
