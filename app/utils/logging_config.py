from loguru import logger
import sys

# P1-SEC-01（2026-10-27）：日志脱敏 filter。
# 此前所有 logger.info/warning/error 直接写盘，token / email / 手机号 / 身份证等
# PII 会以明文落入 logs/healthlens_*.log。现在写入前统一过 pii_sanitizer：
#   - strict=True（默认）：用校验位过滤，少误报——日志是落盘点，宁可漏掉个别
#     畸形号码，也不要误伤订单号 / 随机串等正常业务数字。
#   - 只脱敏 message 本身，不触碰 record 的其它字段（如 exception 溯源），
#     避免 filter 内抛异常拖垮日志管道。
# 诚实边界：pii_sanitizer 规则层对中文人名无能为力（需 Presidio，且生产未装），
# 本 filter 定位是「降低日志泄露面」，不是保证零泄露。见 pii_sanitizer.backend_info()。
from app.utils.pii_sanitizer import sanitize


def _pii_sanitizing_filter(record) -> bool:
    """loguru filter：返回 True 放行；写入前原地脱敏 message。"""
    msg = record.get("message")
    if isinstance(msg, str) and msg:
        try:
            record["message"] = sanitize(msg, use_presidio=False, strict=True)
        except Exception:  # noqa: BLE001
            # 脱敏失败绝不应阻断日志管道（日志是护栏，不是业务）
            pass
    return True


def setup_logging(debug: bool = False):
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    logger.add(
        sys.stderr,
        level=level,
        filter=_pii_sanitizing_filter,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
    logger.add(
        "logs/healthlens_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level=level,
        encoding="utf-8",
        filter=_pii_sanitizing_filter,
    )