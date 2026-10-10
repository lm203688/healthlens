"""TOTP 验证码服务 —— 零外部依赖、零成本。

实现 RFC 6238 (HMAC-SHA1) 与时间步长 30s 的 TOTP，符合 Google Authenticator /
FreeOTP 等标准认证器 App 的 otpauth:// URI 协议。仅依赖 Python 标准库，
无需 pip 安装任何包，因此不会增加部署体积或引入供应链风险。

用途：作为短信/邮件验证码的「其他方式」—— 用户无需提供手机号、
无需配置任何短信/SMTP 服务商，即可用手机上的认证器 App 完成登录二次校验。
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

# 时间步长（秒），与 Google Authenticator 默认一致
PERIOD = 30
# 生成/校验时允许的前后窗口（各 1 个 30s 窗口，容忍时钟漂移）
WINDOW = 1
# 验证码位数
DIGITS = 6
# 密钥字节长度（160-bit，base32 后约 32 字符）
SECRET_BYTES = 20
ISSUER = "HealthLens"


def generate_secret() -> str:
    """生成 base32 编码的随机密钥（去除填充，便于人工抄写）。"""
    raw = secrets.token_bytes(SECRET_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _b32decode(secret: str) -> bytes:
    # base32 标准字符集为大写 A-Z 与 2-7；补齐 '=' 后解码
    s = secret.strip().upper().replace(" ", "")
    padding = (-len(s)) % 8
    return base64.b32decode(s + "=" * padding)


def _hotp(secret_bytes: bytes, counter: int) -> str:
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % (10 ** DIGITS)).zfill(DIGITS)


def current_code(secret: str) -> str:
    counter = int(time.time()) // PERIOD
    return _hotp(_b32decode(secret), counter)


def provisioning_uri(account: str, secret: str, issuer: str = ISSUER) -> str:
    """生成 otpauth://totp/... URI，可直接编码为二维码让认证器 App 扫描。"""
    label = urllib.parse.quote(f"{issuer}:{account}")
    q = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": str(DIGITS),
            "period": str(PERIOD),
        }
    )
    return f"otpauth://totp/{label}?{q}"


def verify(secret: str, code: str, window: int = WINDOW) -> bool:
    """校验 TOTP 码，允许前后 window 个时间步长（容忍时钟漂移）。"""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    try:
        secret_bytes = _b32decode(secret)
    except Exception:
        return False
    counter = int(time.time()) // PERIOD
    codes = {
        _hotp(secret_bytes, counter + i) for i in range(-window, window + 1)
    }
    return code in codes
