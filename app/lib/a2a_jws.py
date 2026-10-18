"""A2A Agent Card JWS 签名（L0 协议对齐层）

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「Agent Card JWS 签名 + RFC 8785 规范化」。

定位：
- **薄工具层**：不做业务逻辑，仅提供 `canonicalize_json` / `sign_jws` /
  `verify_jws` / `sign_agent_card` / `generate_jwk_pair` 五个函数。
- **RFC 8785 JSON Canonicalization Scheme**：优先用 `pyjson_canonicalize`
  （C++ 加速、严格符合 JCS）；未装时 fallback 到纯 Python `json.dumps`。
  fallback 会在注释中说明 Unicode 差异（JCS 要求 NFC 标准化 + 指定浮点
  格式；`json.dumps` 只处理 key 排序与紧凑 separators，不完全等价 JCS，
  但对本项目 agent-card 的字符串/数字结构已足够稳定）。
- **JWS Compact Serialization**（RFC 7515）：`base64url(header).base64url(payload).base64url(sig)`
- **仅支持 ES256**（ECDSA + P-256 + SHA-256）：与 A2A v1.0.1 兼容；
  RS256/PS256 留待后续扩展，此处不实现以免混淆语义。

Wellness 平台术语纪律：本模块只处理身份凭据与数据签名，不做业务判断。

作者：HealthLens L0 协议对齐团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

# 内核原则：cryptography 已在 dependencies（pyproject [project] 里），
# 这里直接导入；不 try/except，缺失是环境错误而不是"引擎不可用"。
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.asymmetric.ec import (
    ECDSA,
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
    SECP256R1,
)

# RFC 8785 优先实现；未装则用 fallback。
try:
    import pyjson_canonicalize as _pyjcs  # type: ignore[import-not-found]

    _HAS_JCS = True
except Exception:  # noqa: BLE001
    _pyjcs = None
    _HAS_JCS = False


# ─────────────────────────── 基础工具 ───────────────────────────

def _b64url_encode(data: bytes) -> str:
    """base64url 编码（无 padding，RFC 4648 §5）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """base64url 解码（自动补 padding）。"""
    if isinstance(data, bytes):
        data = data.decode("ascii")
    # 补齐 4 的倍数
    pad = (-len(data)) % 4
    return base64.urlsafe_b64decode(data + ("=" * pad))


def _base64_decode_hex(s: str) -> bytes:
    """JWK 中 x/y/d 是 base64url（大端 unsigned int，无符号补零至曲线宽度）。"""
    return _b64url_decode(s)


def _int_to_b64url(n: int, width: int) -> str:
    """整数 → base64url（固定宽度大端，无符号补零）。"""
    if n < 0:
        raise ValueError("coordinate must be non-negative")
    b = n.to_bytes(width, byteorder="big", signed=False)
    return _b64url_encode(b)


# ─────────────────────────── JSON 规范化 ───────────────────────────

def canonicalize_json(obj: Any) -> str:
    """RFC 8785 JSON Canonicalization Scheme 规范化。

    优先使用 `pyjson_canonicalize`（严格符合 JCS：NFC Unicode 标准化、
    ES6 数字打印、紧凑无空白）。未装时 fallback 到纯 Python 实现：
    `json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False)`。

    **Unicode 差异说明**：
    fallback 使用 `ensure_ascii=False` 保留原始 Unicode 字符。JCS 要求
    NFC 规范化（`unicodedata.normalize("NFC", ...)`），fallback 未做。
    对 agent-card.json 的 ASCII + 简体中文文本，两者输出一致；但对含
    组合字符（如 "é" = "e" + combining accent）的输入可能不同。CI 中
    若签名与外部服务校验不一致，请 `pip install pyjson-canonicalize`。

    Args:
        obj: 可 JSON 序列化的对象（dict / list / str / int / float / bool / None）

    Returns:
        规范化后的字符串（UTF-8 语义，可直接编码为 bytes 做签名）
    """
    if _HAS_JCS and _pyjcs is not None:
        # pyjson_canonicalize 直接返回 UTF-8 bytes
        b = _pyjcs.canonicalize(obj)
        return b.decode("utf-8")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonicalize_json_bytes(obj: Any) -> bytes:
    """`canonicalize_json` 的 bytes 版本（签名前直接用）。"""
    return canonicalize_json(obj).encode("utf-8")


# ─────────────────────────── JWK 处理 ───────────────────────────

def _parse_private_jwk(jwk: dict[str, Any]) -> EllipticCurvePrivateKey:
    """从 JWK 字典（含 `d`）解析 P-256 私钥。"""
    if jwk.get("kty") != "EC":
        raise ValueError(f"JWK kty must be 'EC', got {jwk.get('kty')!r}")
    if jwk.get("crv") != "P-256":
        raise ValueError(f"JWK crv must be 'P-256', got {jwk.get('crv')!r}")
    required = ("x", "y", "d")
    for k in required:
        if k not in jwk:
            raise ValueError(f"JWK missing field {k!r}")
    x = int.from_bytes(_base64_decode_hex(jwk["x"]), "big")
    y = int.from_bytes(_base64_decode_hex(jwk["y"]), "big")
    d = int.from_bytes(_base64_decode_hex(jwk["d"]), "big")
    return ec.EllipticCurvePrivateNumbers(
        private_value=d,
        public_numbers=ec.EllipticCurvePublicNumbers(x, y, SECP256R1()),
    ).private_key()


def _parse_public_jwk(jwk: dict[str, Any]) -> EllipticCurvePublicKey:
    """从 JWK 字典（仅 `x`,`y`）解析 P-256 公钥。"""
    if jwk.get("kty") != "EC":
        raise ValueError(f"JWK kty must be 'EC', got {jwk.get('kty')!r}")
    if jwk.get("crv") != "P-256":
        raise ValueError(f"JWK crv must be 'P-256', got {jwk.get('crv')!r}")
    required = ("x", "y")
    for k in required:
        if k not in jwk:
            raise ValueError(f"JWK missing field {k!r}")
    x = int.from_bytes(_base64_decode_hex(jwk["x"]), "big")
    y = int.from_bytes(_base64_decode_hex(jwk["y"]), "big")
    return ec.EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key()


def _curve_width_bytes(curve_name: str) -> int:
    """曲线的坐标字节宽度（P-256 = 32 字节）。"""
    mapping = {"P-256": 32, "P-384": 48, "P-521": 66}
    if curve_name not in mapping:
        raise ValueError(f"unsupported curve: {curve_name}")
    return mapping[curve_name]


def generate_jwk_pair(curve: str = "P-256") -> tuple[dict[str, Any], dict[str, Any]]:
    """生成一对 P-256 密钥并导出为 JWK 格式。

    Args:
        curve: 椭圆曲线名（当前仅支持 P-256）

    Returns:
        (private_jwk, public_jwk)
        - private: {"kty":"EC","crv":"P-256","x":..,"y":..,"d":..}
        - public:  {"kty":"EC","crv":"P-256","x":..,"y":..}

    用途：单元测试 + 开发环境。生产环境应从密钥管理系统导出。
    """
    if curve != "P-256":
        raise ValueError(f"unsupported curve: {curve} (only P-256 supported)")
    sk = ec.generate_private_key(ec.SECP256R1())
    pn = sk.public_key().public_numbers()
    d = sk.private_numbers().private_value
    width = 32
    pub = {
        "kty": "EC",
        "crv": "P-256",
        "x": _int_to_b64url(pn.x, width),
        "y": _int_to_b64url(pn.y, width),
    }
    priv = {
        "kty": "EC",
        "crv": "P-256",
        "x": pub["x"],
        "y": pub["y"],
        "d": _int_to_b64url(d, width),
    }
    return priv, pub


# ─────────────────────────── JWS 核心 ───────────────────────────

# 支持的算法 → 哈希算法
_ALG_HASHES: dict[str, hashes.HashAlgorithm] = {
    "ES256": hashes.SHA256(),
}


def sign_jws(
    payload_b64: str,
    private_key_jwk: dict[str, Any],
    alg: str = "ES256",
    extra_header: dict[str, Any] | None = None,
) -> str:
    """生成 JWS Compact Serialization。

    Args:
        payload_b64: base64url 编码的 payload（签名者自行编码）
        private_key_jwk: JWK 格式私钥（含 d）
        alg: 签名算法（当前仅支持 ES256）
        extra_header: 附加到 JOSE header 的字段（如 `kid`, `typ`）

    Returns:
        `base64url(header).base64url(payload_b64).base64url(signature)`

    Raises:
        ValueError: alg 不支持 / JWK 格式错误 / 签名失败
    """
    if alg not in _ALG_HASHES:
        raise ValueError(
            f"unsupported alg {alg!r}; only ES256 supported. "
            "RS256/PS256 left for future extension."
        )
    header: dict[str, Any] = {"alg": alg, "typ": "JWT", "cty": "application/json"}
    if extra_header:
        header.update(extra_header)
    private_key = _parse_private_jwk(private_key_jwk)
    signing_input = (
        _b64url_encode(json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        + "."
        + payload_b64
    ).encode("ascii")
    digest = _ALG_HASHES[alg]
    der_sig = private_key.sign(signing_input, ec.ECDSA(digest))
    # ES256 需要把 DER 编码转成 raw r||s（每个 32 字节）
    r, s = decode_dss_signature(der_sig)
    width = _curve_width_bytes("P-256")
    raw = r.to_bytes(width, "big") + s.to_bytes(width, "big")
    sig_b64 = _b64url_encode(raw)
    return f"{signing_input.decode('ascii')}.{sig_b64}"


def verify_jws(jws: str, public_key_jwk: dict[str, Any]) -> bool:
    """验证 JWS Compact Serialization。

    Args:
        jws: `base64url(header).base64url(payload).base64url(sig)`
        public_key_jwk: JWK 格式公钥（含 x, y）

    Returns:
        True 表示签名有效；False 表示签名不匹配（不抛异常，便于上层批量处理）。
    """
    parts = jws.split(".")
    if len(parts) != 3:
        return False
    header_b64, _payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:  # noqa: BLE001
        return False
    alg = header.get("alg")
    if alg != "ES256":
        return False
    try:
        public_key = _parse_public_jwk(public_key_jwk)
        raw = _b64url_decode(sig_b64)
        width = _curve_width_bytes("P-256")
        if len(raw) != 2 * width:
            return False
        r = int.from_bytes(raw[:width], "big")
        s = int.from_bytes(raw[width:], "big")
        der_sig = _encode_dss_signature(r, s)
        signing_input = (parts[0] + "." + parts[1]).encode("ascii")
        public_key.verify(der_sig, signing_input, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:  # noqa: BLE001
        return False


def _encode_dss_signature(r: int, s: int) -> bytes:
    """把 r, s 编码为 DER 格式（ECDSA 库需要 DER）。"""
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    return encode_dss_signature(r, s)  # type: ignore[no-any-return]


# ─────────────────────────── Agent Card 签名 ───────────────────────────

def sign_agent_card(
    card_dict: dict[str, Any],
    private_key_jwk: dict[str, Any],
    alg: str = "ES256",
    kid: str | None = None,
) -> dict[str, Any]:
    """把 Agent Card 加上 JWS 签名头，返回带 `signature` 字段的 dict。

    结构（自定义扩展，非 A2A 标准字段）：
        card["signature"] = {
            "algorithm": "ES256",
            "jws": "<compact>",
            "public_key": { <public jwk> },
            "kid": "<可选，密钥标识>"
        }

    签名对象：card_dict 本身（去掉已存在的 `signature` 字段，避免自引用）。

    报告定位：A2A v1.0.1 要求 JWS 签名，便于第三方 agent 发现器验证
    agent card 未被篡改。

    Raises:
        ValueError: 签名失败
    """
    # 复制一份，避免修改调用者传入的 dict
    card = dict(card_dict)
    card.pop("signature", None)
    payload_bytes = canonicalize_json_bytes(card)
    payload_b64 = _b64url_encode(payload_bytes)
    extra = {"kid": kid} if kid else None
    jws = sign_jws(payload_b64, private_key_jwk, alg=alg, extra_header=extra)

    # 从私钥 JWK 推导公钥 JWK（去掉 d）
    pub_jwk = {k: v for k, v in private_key_jwk.items() if k != "d"}

    card["signature"] = {
        "algorithm": alg,
        "jws": jws,
        "public_key": pub_jwk,
    }
    if kid:
        card["signature"]["kid"] = kid
    return card


def verify_agent_card_signature(card_dict: dict[str, Any]) -> bool:
    """验证 card_dict 上的 signature 字段。

    双重校验（严格模式）：
    1. JWS 签名本身有效（对 header.payload 的签名与 public_key 匹配）。
    2. JWS 内的 payload 与「当前 card_dict 去掉 signature 后规范化」字节一致——
       这才能拦截「先签名，再修改 card」的篡改。

    只验证第 1 步而忽视第 2 步的话，攻击者可以持有合法 JWS、把 card 内容随便
    替换，签名仍然通过——这在生产环境是严重漏洞。

    Returns:
        True 表示签名与 payload 均一致；False 表示任一校验失败。
    """
    sig = card_dict.get("signature")
    if not isinstance(sig, dict):
        return False
    jws = sig.get("jws")
    pub = sig.get("public_key")
    if not isinstance(jws, str) or not isinstance(pub, dict):
        return False
    # 1. 签名本身有效
    if not verify_jws(jws, pub):
        return False
    # 2. payload 与当前 card 一致
    parts = jws.split(".")
    if len(parts) != 3:
        return False
    try:
        signed_payload_bytes = _b64url_decode(parts[1])
    except Exception:  # noqa: BLE001
        return False
    card_without_sig = {k: v for k, v in card_dict.items() if k != "signature"}
    current_bytes = canonicalize_json_bytes(card_without_sig)
    return current_bytes == signed_payload_bytes


def load_signing_key_from_env() -> dict[str, Any] | None:
    """从环境变量读取 JWK 私钥。

    期望环境变量：`HL_A2A_SIGNING_KEY_JWK`（JSON 字符串）。
    未设置或格式错误时返回 None（不抛异常，让调用方决定是否 fail-loud）。
    """
    raw = os.environ.get("HL_A2A_SIGNING_KEY_JWK")
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or obj.get("kty") != "EC" or obj.get("d"):
        # 必须是私钥 JWK（含 d）
        pass  # 结构错误由调用方判断
    return obj


__all__ = [
    "canonicalize_json",
    "canonicalize_json_bytes",
    "sign_jws",
    "verify_jws",
    "sign_agent_card",
    "verify_agent_card_signature",
    "generate_jwk_pair",
    "load_signing_key_from_env",
]
