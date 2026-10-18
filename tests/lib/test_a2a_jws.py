"""L0 A2A JWS 签名测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L0。
> 「Agent Card JWS 签名 + RFC 8785 规范化」。

覆盖：
- JSON 规范化确定性（顺序无关）
- Round-trip（sign → verify → tamper → verify fail）
- 字典顺序无关性
- generate_jwk_pair 生成合法 JWK
- Agent Card 签名与篡改检测
- 不支持的算法 fail-loud
- Unicode 处理
- Empty payload / dict ordering
"""
from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.lib.a2a_jws import (
    canonicalize_json,
    canonicalize_json_bytes,
    generate_jwk_pair,
    sign_agent_card,
    sign_jws,
    verify_agent_card_signature,
    verify_jws,
)


# ─────────────────────────── Fixtures ───────────────────────────

@pytest.fixture(scope="module")
def jwk_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    return generate_jwk_pair()


@pytest.fixture
def simple_payload() -> str:
    return base64.urlsafe_b64encode(b'{"hello":"world"}').rstrip(b"=").decode()


# ─────────────────────────── 1. generate_jwk_pair ───────────────────────────

class TestGenerateJwkPair:
    """P-256 JWK 对生成。"""

    def test_returns_two_dicts(self, jwk_pair) -> None:
        priv, pub = jwk_pair
        assert isinstance(priv, dict)
        assert isinstance(pub, dict)

    def test_private_has_d(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        assert "d" in priv
        assert "x" in priv
        assert "y" in priv

    def test_public_no_d(self, jwk_pair) -> None:
        _, pub = jwk_pair
        assert "d" not in pub
        assert "x" in pub
        assert "y" in pub

    def test_kty_is_EC(self, jwk_pair) -> None:
        priv, pub = jwk_pair
        assert priv["kty"] == "EC"
        assert pub["kty"] == "EC"

    def test_crv_is_P256(self, jwk_pair) -> None:
        priv, pub = jwk_pair
        assert priv["crv"] == "P-256"
        assert pub["crv"] == "P-256"

    def test_xy_shared(self, jwk_pair) -> None:
        priv, pub = jwk_pair
        assert priv["x"] == pub["x"]
        assert priv["y"] == pub["y"]

    def test_coords_are_base64url(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        # base64url 不含 +, /, =
        for coord in ("x", "y", "d"):
            v = priv[coord]
            assert "+" not in v
            assert "/" not in v
            assert "=" not in v

    def test_coords_are_32_bytes(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        for coord in ("x", "y", "d"):
            raw = base64.urlsafe_b64decode(priv[coord] + "==")
            assert len(raw) == 32, f"{coord} should be 32 bytes, got {len(raw)}"

    def test_two_calls_generate_different_keys(self) -> None:
        a, _ = generate_jwk_pair()
        b, _ = generate_jwk_pair()
        assert a["d"] != b["d"]
        assert a["x"] != b["x"]


# ─────────────────────────── 2. canonicalize_json ───────────────────────────

class TestCanonicalizeJson:
    """RFC 8785 规范化（或 fallback）。"""

    def test_dict_order_independent(self) -> None:
        a = {"b": 1, "a": 2, "c": 3}
        b = {"a": 2, "c": 3, "b": 1}
        assert canonicalize_json(a) == canonicalize_json(b)

    def test_compact_no_whitespace(self) -> None:
        out = canonicalize_json({"a": 1, "b": [1, 2]})
        # fallback 用 separators=(",",":"), 无空格
        assert ": " not in out
        assert ", " not in out

    def test_nested_dict(self) -> None:
        a = {"outer": {"z": 1, "a": 2}}
        b = {"outer": {"a": 2, "z": 1}}
        assert canonicalize_json(a) == canonicalize_json(b)

    def test_string_values(self) -> None:
        out = canonicalize_json({"greeting": "hello 你好"})
        # 应为 UTF-8 语义，中文保留
        assert "你好" in out or "\\u4f60\\u597d" in out

    def test_numbers_preserved(self) -> None:
        out = canonicalize_json({"int": 5, "float": 1.5, "neg": -3})
        assert '"int":5' in out
        assert '"float":1.5' in out
        assert '"neg":-3' in out

    def test_bool_and_null(self) -> None:
        out = canonicalize_json({"b": True, "n": None})
        assert '"b":true' in out
        assert '"n":null' in out

    def test_list_order_preserved(self) -> None:
        # 列表顺序**是**语义的一部分
        a = {"l": [1, 2, 3]}
        b = {"l": [3, 2, 1]}
        assert canonicalize_json(a) != canonicalize_json(b)

    def test_bytes_output_matches_str(self) -> None:
        obj = {"k": "v"}
        s = canonicalize_json(obj)
        b = canonicalize_json_bytes(obj)
        assert b == s.encode("utf-8")

    def test_unicode_stable(self) -> None:
        # 混合 CJK + Latin
        out1 = canonicalize_json({"name": "健康 Health"})
        out2 = canonicalize_json({"name": "健康 Health"})
        assert out1 == out2


# ─────────────────────────── 3. sign_jws / verify_jws ───────────────────────────

class TestSignVerify:
    """JWS Compact Serialization round-trip。"""

    def test_sign_returns_three_parts(self, simple_payload: str, jwk_pair) -> None:
        priv, _ = jwk_pair
        jws = sign_jws(simple_payload, priv)
        assert jws.count(".") == 2

    def test_verify_ok(self, simple_payload: str, jwk_pair) -> None:
        priv, pub = jwk_pair
        jws = sign_jws(simple_payload, priv)
        assert verify_jws(jws, pub) is True

    def test_verify_tampered_payload_fails(self, simple_payload: str, jwk_pair) -> None:
        priv, pub = jwk_pair
        jws = sign_jws(simple_payload, priv)
        # 修改 payload（第 2 段）
        parts = jws.split(".")
        tampered = parts[0] + "." + "eyJmb29jb3JydXB0ZWR" + "." + parts[2]
        assert verify_jws(tampered, pub) is False

    def test_verify_tampered_header_fails(self, simple_payload: str, jwk_pair) -> None:
        priv, pub = jwk_pair
        jws = sign_jws(simple_payload, priv)
        parts = jws.split(".")
        # 改 header 里的 alg
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
        header["alg"] = "HS256"
        new_header_b64 = base64.urlsafe_b64encode(
            json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        tampered = new_header_b64 + "." + parts[1] + "." + parts[2]
        assert verify_jws(tampered, pub) is False

    def test_verify_tampered_sig_fails(self, simple_payload: str, jwk_pair) -> None:
        priv, pub = jwk_pair
        jws = sign_jws(simple_payload, priv)
        parts = jws.split(".")
        # 最后一字符改一下
        last = parts[2]
        last_mod = "x" + last[1:] if last[0] != "x" else "y" + last[1:]
        tampered = parts[0] + "." + parts[1] + "." + last_mod
        assert verify_jws(tampered, pub) is False

    def test_verify_wrong_key_fails(self, simple_payload: str) -> None:
        priv, _ = generate_jwk_pair()
        _, other_pub = generate_jwk_pair()
        jws = sign_jws(simple_payload, priv)
        assert verify_jws(jws, other_pub) is False

    def test_verify_invalid_format_fails(self, jwk_pair) -> None:
        _, pub = jwk_pair
        assert verify_jws("no-dot-here", pub) is False
        assert verify_jws("a.b", pub) is False
        assert verify_jws("", pub) is False
        assert verify_jws("a.b.c.d", pub) is False

    def test_verify_bad_json_header_fails(self, simple_payload: str, jwk_pair) -> None:
        _, pub = jwk_pair
        bad_header = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
        assert verify_jws(f"{bad_header}.{simple_payload}.x", pub) is False

    def test_two_signatures_both_verify(self, simple_payload: str, jwk_pair) -> None:
        """同 payload + 同私钥，两次签名可各自通过 verify。

        Python cryptography 库默认用随机 nonce（非 RFC 6979），
        所以两次签名字节可能不同，但**都**能通过 verify。
        """
        priv, pub = jwk_pair
        j1 = sign_jws(simple_payload, priv)
        j2 = sign_jws(simple_payload, priv)
        assert verify_jws(j1, pub) is True
        assert verify_jws(j2, pub) is True
        # payload + header 部分相同，只有 sig 段可能不同
        assert j1.split(".")[:2] == j2.split(".")[:2]


# ─────────────────────────── 4. Extra headers ───────────────────────────

class TestExtraHeaders:
    """JOSE header 扩展字段。"""

    def test_kid_in_header(self, simple_payload: str, jwk_pair) -> None:
        priv, _ = jwk_pair
        jws = sign_jws(simple_payload, priv, extra_header={"kid": "key-1"})
        header_b64 = jws.split(".")[0]
        header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
        assert header["kid"] == "key-1"

    def test_multiple_extra_headers(self, simple_payload: str, jwk_pair) -> None:
        priv, _ = jwk_pair
        jws = sign_jws(simple_payload, priv, extra_header={"kid": "a", "x-custom": 42})
        header_b64 = jws.split(".")[0]
        header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
        assert header["kid"] == "a"
        assert header["x-custom"] == 42


# ─────────────────────────── 5. 错误处理 ───────────────────────────

class TestErrors:
    """错误输入 fail-loud。"""

    def test_unsupported_alg_raises(self, simple_payload: str, jwk_pair) -> None:
        priv, _ = jwk_pair
        with pytest.raises(ValueError, match="unsupported alg"):
            sign_jws(simple_payload, priv, alg="RS256")

    def test_rs256_raises(self, simple_payload: str, jwk_pair) -> None:
        priv, _ = jwk_pair
        with pytest.raises(ValueError):
            sign_jws(simple_payload, priv, alg="RS256")

    def test_invalid_jwk_kty_raises(self, simple_payload: str) -> None:
        bad_jwk = {"kty": "RSA", "n": "x", "e": "AQAB"}
        with pytest.raises(ValueError, match="kty"):
            sign_jws(simple_payload, bad_jwk)

    def test_invalid_jwk_crv_raises(self, simple_payload: str) -> None:
        bad_jwk = {"kty": "EC", "crv": "P-521", "x": "x", "y": "y", "d": "z"}
        with pytest.raises(ValueError, match="crv"):
            sign_jws(simple_payload, bad_jwk)

    def test_missing_d_raises(self, simple_payload: str) -> None:
        bad_jwk = {"kty": "EC", "crv": "P-256", "x": "x", "y": "y"}
        with pytest.raises(ValueError, match="d"):
            sign_jws(simple_payload, bad_jwk)

    def test_generate_unsupported_curve_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported curve"):
            generate_jwk_pair(curve="P-521")


# ─────────────────────────── 6. sign_agent_card ───────────────────────────

class TestSignAgentCard:
    """Agent Card 签名端到端。"""

    def test_sign_returns_signature_field(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        card = {"name": "HL", "version": "1.0"}
        signed = sign_agent_card(card, priv)
        assert "signature" in signed
        sig = signed["signature"]
        assert sig["algorithm"] == "ES256"
        assert "jws" in sig
        assert "public_key" in sig
        assert sig["public_key"]["kty"] == "EC"
        assert sig["public_key"]["crv"] == "P-256"

    def test_sign_does_not_mutate_input(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        card = {"name": "HL", "version": "1.0"}
        original = dict(card)
        _ = sign_agent_card(card, priv)
        assert card == original

    def test_verify_signed_card_ok(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card({"name": "HL", "version": "1.0"}, priv)
        assert verify_agent_card_signature(signed) is True

    def test_tampered_card_fails_verify(self, jwk_pair) -> None:
        """核心篡改检测：签名后修改 card 内容，verify 必须失败。"""
        priv, _ = jwk_pair
        signed = sign_agent_card({"name": "HL", "version": "1.0"}, priv)
        signed["name"] = "Hacked"
        assert verify_agent_card_signature(signed) is False

    def test_tampered_signature_field_fails(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card({"name": "HL", "version": "1.0"}, priv)
        signed["signature"]["jws"] = signed["signature"]["jws"][:-3] + "xxx"
        assert verify_agent_card_signature(signed) is False

    def test_missing_signature_fails(self) -> None:
        assert verify_agent_card_signature({"name": "HL"}) is False

    def test_empty_signature_fails(self) -> None:
        assert verify_agent_card_signature({"name": "HL", "signature": {}}) is False

    def test_signature_with_kid(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card({"name": "HL"}, priv, kid="main")
        assert signed["signature"]["kid"] == "main"
        assert verify_agent_card_signature(signed) is True

    def test_signature_with_unicode_content(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        card = {"name": "健康", "description": "整合医学 wellness"}
        signed = sign_agent_card(card, priv)
        assert verify_agent_card_signature(signed) is True

    def test_signature_with_nested_content(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        card = {
            "name": "HL",
            "skills": [{"id": "a", "tags": ["x", "y"]}],
            "capabilities": {"extensions": [{"uri": "https://x"}]},
        }
        signed = sign_agent_card(card, priv)
        assert verify_agent_card_signature(signed) is True
        # Tamper nested
        signed["skills"][0]["id"] = "hacked"
        assert verify_agent_card_signature(signed) is False

    def test_two_keys_cross_verify_fail(self) -> None:
        priv_a, _ = generate_jwk_pair()
        priv_b, _ = generate_jwk_pair()
        signed_a = sign_agent_card({"name": "A"}, priv_a)
        # 篡改后应该 fail
        signed_a["name"] = "B"
        assert verify_agent_card_signature(signed_a) is False
        # 用 priv_b 重签
        signed_b = sign_agent_card({"name": "A"}, priv_b)
        assert verify_agent_card_signature(signed_b) is True
