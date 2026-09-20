"""简化版运行时审计（wellness 平台轻量自检）

设计目标：零依赖、零外部服务，仅对「输入/输出文本 + 推荐证据等级」做 4 类
轻量异常检测，命中写入 audit_events 表，供 /api/v1/audit 端点巡检。

检测范围（不是全量安全系统，只是护栏）：
  1. sensitive_info_leak   输出疑似泄露 手机号/邮箱/身份证
  2. out_of_bounds_evidence 个性化推荐出现越界证据等级（L4 等不应进个性化）
  3. input_anomaly         用户输入超长 / 含控制字符
  4. output_anomaly        输出超长 / 高重复，疑似失控生成
"""
import re

# 手机号（中国大陆）
_RE_PHONE = re.compile(r"1[3-9]\d{9}")
# 邮箱
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 身份证（18 位，末位可为 X）
_RE_IDCARD = re.compile(r"\b\d{17}[\dXx]\b")

# 控制字符（除常见空白外）
_RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

INPUT_MAX_LEN = 2000
OUTPUT_MAX_LEN = 8000
REPETITION_THRESHOLD = 0.6  # 单 token 重复占比阈值


def scan_sensitive(text: str) -> list[str]:
    """扫描文本中的敏感信息模式，返回命中类型列表。"""
    hits = []
    if _RE_PHONE.search(text or ""):
        hits.append("phone")
    if _RE_EMAIL.search(text or ""):
        hits.append("email")
    if _RE_IDCARD.search(text or ""):
        hits.append("idcard")
    return hits


def detect_input_anomaly(text: str) -> str | None:
    if not text:
        return None
    if len(text) > INPUT_MAX_LEN:
        return f"input_too_long:{len(text)}"
    if _RE_CTRL.search(text):
        return "input_control_chars"
    return None


def detect_output_anomaly(text: str) -> str | None:
    if not text:
        return None
    if len(text) > OUTPUT_MAX_LEN:
        return f"output_too_long:{len(text)}"
    # 重复模式检测：按标点/空白切分后，最高频 token 占比
    tokens = re.split(r"[\s，。、；：！？,.!?;:]+", text)
    tokens = [t for t in tokens if t]
    if len(tokens) >= 20:
        from collections import Counter
        most = Counter(tokens).most_common(1)[0][1]
        ratio = most / len(tokens)
        if ratio > REPETITION_THRESHOLD:
            return f"high_repetition:{round(ratio, 2)}"
    return None


def check_evidence_bounds(recommendations: list[dict] | None) -> list[str]:
    """个性化推荐中不应出现 L4（仅假说/无现代证据）。"""
    bad = []
    for r in (recommendations or []):
        lvl = (r or {}).get("evidence_level")
        mode = (r or {}).get("mode")
        if mode == "personalized" and lvl in ("L4", "L5"):
            bad.append(r.get("case_id", "?"))
    return bad


def build_events(
    endpoint: str,
    user_id: str | None,
    input_text: str = "",
    output_text: str = "",
    recommendations: list[dict] | None = None,
) -> list[dict]:
    """返回命中的审计事件列表（dict，待持久化）。"""
    events: list[dict] = []

    # 1. 敏感信息泄露
    sens = scan_sensitive(output_text)
    if sens:
        events.append({
            "user_id": user_id,
            "endpoint": endpoint,
            "event_type": "sensitive_info_leak",
            "severity": 3,
            "detail": "输出命中敏感模式: " + ", ".join(sens),
        })

    # 2. 推荐证据越界
    bad = check_evidence_bounds(recommendations)
    if bad:
        events.append({
            "user_id": user_id,
            "endpoint": endpoint,
            "event_type": "out_of_bounds_evidence",
            "severity": 2,
            "detail": "个性化推荐含越界证据等级: " + ", ".join(bad),
        })

    # 3. 输入异常
    ia = detect_input_anomaly(input_text)
    if ia:
        events.append({
            "user_id": user_id,
            "endpoint": endpoint,
            "event_type": "input_anomaly",
            "severity": 1,
            "detail": ia,
        })

    # 4. 输出异常
    oa = detect_output_anomaly(output_text)
    if oa:
        events.append({
            "user_id": user_id,
            "endpoint": endpoint,
            "event_type": "output_anomaly",
            "severity": 2,
            "detail": oa,
        })

    return events


async def persist_events(db, events: list[dict]) -> int:
    """将审计事件写入数据库，返回写入条数。失败静默返回 0。"""
    if not events:
        return 0
    from app.models.audit_event import AuditEvent
    try:
        for e in events:
            db.add(AuditEvent(**e))
        await db.commit()
        return len(events)
    except Exception:
        # 审计失败绝不应阻断主业务
        try:
            await db.rollback()
        except Exception:
            pass
        return 0
