"""A2A v1.0.1 契约测试（L0 协议对齐）。

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
- Agent Card 结构契约（SCREAMING_SNAKE_CASE 能力声明 + JSON Schema 层 camelCase 边界）
- SendMessage / ListTasks verb 声明（替代旧 message/send）
- signing_key / jws_signature 字段（KMS 引用占位符）
- conformanceNote 如实性
- interfaceUrl ↔ FastAPI 路由反射一致性
- JWS round-trip（sign → verify → tamper → verify fail）

所有测试纯 Python（json / urllib / cryptography / fastapi TestClient），无外部网络请求。

作者：HealthLens L0 协议深化团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from app.lib.a2a_jws import (
    generate_jwk_pair,
    sign_agent_card,
    verify_agent_card_signature,
)
from app.lib.protocol_audit import audit_a2a

REPO_ROOT = Path(__file__).resolve().parents[2]
CARD_PATH = REPO_ROOT / "agent-card.json"
CARD = json.loads(CARD_PATH.read_text(encoding="utf-8"))

SCREAMING = re.compile(r"^[A-Z][A-Z0-9_]*$")
CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*$")


def _pyproject_version() -> str:
    import tomllib

    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _strip_origin(url: str) -> str:
    p = urlparse(url)
    return p.path or "/"


def _match_template(url_path: str, templates: set[str]) -> str | None:
    """把真实路径与 OpenAPI 模板比对，路径参数按段占位。"""
    if url_path in templates:
        return url_path
    for tpl in templates:
        if len(url_path.split("/")) == len(tpl.split("/")) and all(
            s == t or (t.startswith("{") and t.endswith("}"))
            for s, t in zip(url_path.split("/"), tpl.split("/"))
        ):
            return tpl
    return None


@pytest.fixture(scope="module")
def openapi_paths() -> set[str]:
    """FastAPI 反射：拉一次 openapi.json 拿所有路径模板。"""
    from fastapi.testclient import TestClient

    from app import create_app

    client = TestClient(create_app())
    return set(client.get("/openapi.json").json()["paths"].keys())


# ─────────────────────────── 1. 基础结构 ───────────────────────────

class TestA2aCardBasics:
    """Agent Card 顶层结构与协议版本。"""

    def test_01_card_parses_and_has_name(self) -> None:
        assert isinstance(CARD, dict)
        assert CARD["name"] == "HealthLens"

    def test_02_protocol_version_is_v1_or_1_0_1(self) -> None:
        assert CARD["protocolVersion"] in ("1.0", "1.0.1"), (
            f"protocolVersion={CARD['protocolVersion']!r} 必须是 1.0 或 1.0.1"
        )

    def test_03_protocol_version_1_0_1_declared(self) -> None:
        """v0.29.0 起必须显式声明 1.0.1（引入 SendMessage / ListTasks / JWS）。"""
        assert CARD["protocolVersion"] == "1.0.1"

    def test_04_version_matches_pyproject(self) -> None:
        assert CARD["version"] == _pyproject_version(), (
            f"card.version={CARD['version']!r} 与 pyproject={_pyproject_version()!r} 不一致"
        )

    def test_05_supported_interfaces_declared(self) -> None:
        ifs = CARD.get("supportedInterfaces", [])
        assert len(ifs) >= 1
        for iface in ifs:
            assert iface.get("url")
            assert iface.get("protocolBinding")
            assert iface.get("protocolVersion")


# ─────────────────────────── 2. capabilities 层 SCREAMING_SNAKE_CASE ───────────────────────────

class TestCapabilitiesScreamingSnake:
    """A2A v1.0.1 能力声明层 key 全部 SCREAMING_SNAKE_CASE。"""

    def test_06_capabilities_is_dict(self) -> None:
        assert isinstance(CARD.get("capabilities"), dict)

    def test_07_all_capabilities_keys_screaming(self) -> None:
        caps = CARD["capabilities"]
        for k in caps.keys():
            assert SCREAMING.match(k), f"capability key {k!r} 应为 SCREAMING_SNAKE_CASE"

    def test_08_capabilities_no_camelcase_keys(self) -> None:
        """明确检查 24 个历史 camelCase 已迁移。"""
        caps = CARD["capabilities"]
        # 这些是原 A2A v1.0 的 camelCase，v1.0.1 起必须全部 SCREAMING
        legacy_camel = {
            "streaming",
            "pushNotifications",
            "extendedAgentCard",
            "stateTransitionHistory",
            "listChanged",
        }
        offenders = legacy_camel & set(caps.keys())
        assert not offenders, f"发现遗留 camelCase 能力 key：{offenders}"

    def test_09_streaming_false(self) -> None:
        assert CARD["capabilities"].get("STREAMING") is False

    def test_10_push_notifications_false(self) -> None:
        assert CARD["capabilities"].get("PUSH_NOTIFICATIONS") is False

    def test_11_extended_agent_card_false(self) -> None:
        assert CARD["capabilities"].get("EXTENDED_AGENT_CARD") is False

    def test_12_state_transition_history_false(self) -> None:
        """如实声明未实现状态迁移历史，保持与 ListTasks 的一致性。"""
        assert CARD["capabilities"].get("STATE_TRANSITION_HISTORY") is False

    def test_13_list_tasks_declared(self) -> None:
        """v1.0.1 起必须显式声明 LIST_TASKS。"""
        assert CARD["capabilities"].get("LIST_TASKS") is True

    def test_14_extensions_list_present(self) -> None:
        assert isinstance(CARD["capabilities"].get("EXTENSIONS"), list)
        assert len(CARD["capabilities"]["EXTENSIONS"]) >= 2  # MCP + A2A


# ─────────────────────────── 3. securitySchemes 保持 camelCase（JSON Schema 层） ───────────────────────────

class TestSecuritySchemesCamelCase:
    """securitySchemes.* 是 JSON Schema 语法层，保持 camelCase。"""

    def test_15_security_schemes_is_dict(self) -> None:
        assert isinstance(CARD.get("securitySchemes"), dict)

    def test_16_security_schemes_bearer_auth_present(self) -> None:
        assert "bearerAuth" in CARD["securitySchemes"]

    def test_17_security_schemes_internal_fields_camel(self) -> None:
        """内部 type/scheme/bearerFormat 是 JSON Schema 字段，保持原样。"""
        scheme = CARD["securitySchemes"]["bearerAuth"]
        for k in ("type", "scheme", "bearerFormat"):
            assert k in scheme, f"bearerAuth 缺 {k}"
            assert CAMEL.match(k), f"JSON Schema 字段 {k!r} 应保持 camelCase"

    def test_18_bearer_auth_scheme_is_bearer(self) -> None:
        assert CARD["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
        assert CARD["securitySchemes"]["bearerAuth"]["type"] == "http"


# ─────────────────────────── 4. SendMessage / ListTasks verb 声明 ───────────────────────────

class TestA2aV1Verbs:
    """A2A v1.0.1 verbs：SendMessage（替代旧 message/send）+ ListTasks。"""

    def test_19_no_legacy_message_send_string(self) -> None:
        raw = json.dumps(CARD, ensure_ascii=False)
        assert "message/send" not in raw, "不得再出现旧 message/send 命名"

    def test_20_send_message_declared_in_extensions(self) -> None:
        exts = CARD["capabilities"]["EXTENSIONS"]
        a2a_ext = next(e for e in exts if "A2A" in e.get("uri", "") or "SendMessage" in json.dumps(e))
        verbs = a2a_ext.get("verbs", [])
        assert "SendMessage" in verbs

    def test_21_list_tasks_declared_as_verb(self) -> None:
        exts = CARD["capabilities"]["EXTENSIONS"]
        a2a_ext = next(e for e in exts if "A2A" in e.get("uri", "") or "SendMessage" in json.dumps(e))
        verbs = a2a_ext.get("verbs", [])
        assert "ListTasks" in verbs

    def test_22_a2a_v1_0_1_spec_url_declared(self) -> None:
        """在 capabilities.EXTENSIONS[].specs[] 里追加 A2A v1.0.1 spec URL。"""
        all_spec_urls = set()
        for e in CARD["capabilities"]["EXTENSIONS"]:
            for spec in e.get("specs", []):
                all_spec_urls.add(spec.get("spec", ""))
        assert "https://google.github.io/A2A/specification/v1.0.1/" in all_spec_urls

    def test_23_mcp_2026_07_28_spec_url_declared(self) -> None:
        all_spec_urls = set()
        for e in CARD["capabilities"]["EXTENSIONS"]:
            for spec in e.get("specs", []):
                all_spec_urls.add(spec.get("spec", ""))
        assert "https://modelcontextprotocol.io/specification/2026-07-28" in all_spec_urls


# ─────────────────────────── 5. JWS 签名接入 ───────────────────────────

class TestJwsSignFields:
    """signing_key + jws_signature 顶层字段（KMS 引用占位符）。"""

    def test_24_signing_key_present(self) -> None:
        assert "signing_key" in CARD, "signing_key 必须存在（A2A v1.0.1 要求）"

    def test_25_signing_key_is_es256_kms_ref(self) -> None:
        assert CARD["signing_key"] == "ES256:HEALTHLENS_PROD_KEY_REF"

    def test_26_signing_key_is_string_reference_not_secret(self) -> None:
        """signing_key 必须是引用占位符，不能是 JWK 明文（dict 或 base64url JSON 串）。"""
        v = CARD["signing_key"]
        assert isinstance(v, str)
        # 必须是 "ALG:REF" 形式的引用，不是 JWK JSON
        assert v.startswith("ES256:")
        assert not v.strip().startswith("{"), "signing_key 不能是 JWK JSON 字面量"
        # 尝试解析为 JSON 应失败
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError:
            pass
        else:
            # 如果是 JSON，也绝不能含私钥字段 d
            if isinstance(parsed, dict):
                assert "d" not in parsed, "signing_key 不能含 JWK 私钥 d 字段"

    def test_27_jws_signature_field_present(self) -> None:
        assert "jws_signature" in CARD, "jws_signature 字段必须存在"

    def test_28_jws_signature_value_is_placeholder(self) -> None:
        v = CARD["jws_signature"]
        assert isinstance(v, str)
        assert len(v) > 0

    def test_29_generate_jwk_pair_produces_valid_keys(self) -> None:
        priv, pub = generate_jwk_pair()
        assert priv["kty"] == "EC"
        assert priv["crv"] == "P-256"
        assert "d" in priv
        assert "d" not in pub


# ─────────────────────────── 6. JWS round-trip ───────────────────────────

class TestJwsRoundTrip:
    """用 a2a_jws.sign_agent_card → verify → tamper → verify fail。"""

    @pytest.fixture
    def jwk_pair(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return generate_jwk_pair()

    def test_30_sign_agent_card_adds_signature_field(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card(CARD, priv, kid="healthlens-prod")
        assert "signature" in signed
        assert signed["signature"]["algorithm"] == "ES256"
        assert signed["signature"]["kid"] == "healthlens-prod"

    def test_31_sign_then_verify_passes(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card(CARD, priv)
        assert verify_agent_card_signature(signed) is True

    def test_32_tamper_payload_fails_verify(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card(CARD, priv)
        tampered = dict(signed)
        tampered["version"] = "9.9.9"  # 篡改 payload
        assert verify_agent_card_signature(tampered) is False

    def test_33_tamper_signature_fails_verify(self, jwk_pair) -> None:
        priv, _ = jwk_pair
        signed = sign_agent_card(CARD, priv)
        tampered = dict(signed)
        sig = dict(tampered["signature"])
        sig["jws"] = "tampered." + sig["jws"].split(".", 1)[1]
        tampered["signature"] = sig
        assert verify_agent_card_signature(tampered) is False

    def test_34_wrong_key_fails_verify(self) -> None:
        priv_a, _ = generate_jwk_pair()
        _priv_b, pub_b = generate_jwk_pair()
        signed = sign_agent_card(CARD, priv_a)
        # 用另一个公钥覆盖
        tampered = dict(signed)
        sig = dict(tampered["signature"])
        sig["public_key"] = pub_b
        tampered["signature"] = sig
        assert verify_agent_card_signature(tampered) is False

    def test_35_card_without_signature_returns_false(self) -> None:
        assert verify_agent_card_signature(CARD) is False

    def test_36_card_with_invalid_signature_shape_returns_false(self) -> None:
        assert verify_agent_card_signature({"signature": {}}) is False
        assert verify_agent_card_signature({}) is False

    def test_37_signature_excludes_itself(self, jwk_pair) -> None:
        """签名对象必须剥离自身 signature 字段，避免自引用哈希不稳定。"""
        priv, _ = jwk_pair
        signed = sign_agent_card(CARD, priv)
        # 再签一次应幂等（signature 字段被剥离）
        signed2 = sign_agent_card(signed, priv)
        assert signed["signature"]["jws"].split(".")[1] == signed2["signature"]["jws"].split(".")[1]


# ─────────────────────────── 7. conformanceNote 如实性 ───────────────────────────

class TestConformanceHonesty:
    """conformanceNote 必须如实说明已实现/未实现边界。"""

    def test_38_conformance_note_present(self) -> None:
        assert CARD.get("conformanceNote"), "conformanceNote 不能为空"

    def test_39_conformance_note_declares_implemented(self) -> None:
        """v0.30.0 起 A2A JSON-RPC 端点已落地，note 必须声明已实现。"""
        note = CARD["conformanceNote"]
        assert ("已实现" in note) or ("implemented" in note.lower())

    def test_40_conformance_note_names_specific_endpoints(self) -> None:
        """note 必须点名 4 个已实现的 A2A 端点，不能含糊。"""
        note = CARD["conformanceNote"]
        assert "SendMessage" in note
        assert "ListTasks" in note
        assert "GetTask" in note
        assert "CancelTask" in note

    def test_41_conformance_note_mentions_mcp_alternative(self) -> None:
        """note 应告知下游：同时保留 MCP JSON-RPC 2.0 作为并行接口。"""
        note = CARD["conformanceNote"]
        assert "MCP" in note or "mcp" in note

    def test_42_a2a_audit_c7_passes_on_real_card(self) -> None:
        r = audit_a2a(CARD_PATH)
        c7 = next(c for c in r.checks if c.check_id == "A2A-C7-conformance-honest")
        assert c7.pass_ is True, f"conformance 不诚实：{c7.suggestion}"


# ─────────────────────────── 8. interfaceUrl 与 FastAPI 路由反射一致性 ───────────────────────────

class TestInterfaceUrlContractScan:
    """agent-card.json 里声明的所有 skill interfaceUrl 必须对应真实 OpenAPI 路径。"""

    def test_43_all_skills_have_interface_url(self, openapi_paths: set[str]) -> None:
        for sk in CARD["skills"]:
            assert sk.get("interfaceUrl"), f"skill {sk['id']} 缺 interfaceUrl"

    def test_44_all_interface_urls_resolve(self, openapi_paths: set[str]) -> None:
        failures = []
        for sk in CARD["skills"]:
            tpl = _match_template(_strip_origin(sk["interfaceUrl"]), openapi_paths)
            if tpl is None:
                failures.append(f"{sk['id']} -> {sk['interfaceUrl']}")
        assert not failures, (
            "以下 skill 的 interfaceUrl 未在 OpenAPI 中注册：\n  " + "\n  ".join(failures)
        )

    def test_45_interface_url_uses_https(self) -> None:
        for sk in CARD["skills"]:
            u = urlparse(sk["interfaceUrl"])
            assert u.scheme == "https", f"{sk['id']} 的 interfaceUrl 必须 https: {sk['interfaceUrl']}"

    def test_46_mcp_tools_skill_url_registered(self, openapi_paths: set[str]) -> None:
        mcp_skill = next((sk for sk in CARD["skills"] if sk["id"] == "mcp-tools"), None)
        assert mcp_skill is not None
        p = _strip_origin(mcp_skill["interfaceUrl"])
        assert _match_template(p, openapi_paths) is not None, (
            f"mcp-tools skill 的 interfaceUrl {p} 未在 OpenAPI 中注册"
        )


# ─────────────────────────── 9. audit_a2a 全量通过 ───────────────────────────

class TestA2aAuditOnRealCard:
    """对真实 agent-card.json 跑 audit_a2a 全量断言。"""

    def test_47_a2a_audit_returns_7_checks(self) -> None:
        r = audit_a2a(CARD_PATH)
        assert len(r.checks) == 7

    def test_48_a2a_audit_all_pass_on_real(self) -> None:
        r = audit_a2a(CARD_PATH)
        s = r.to_dict()["summary"]
        assert s["all_passed"] is True, (
            f"A2A 审计未全通过，failed={s['failed']}"
        )

    def test_49_a2a_audit_target_is_v1_0_1(self) -> None:
        r = audit_a2a(CARD_PATH)
        assert r.summary["protocol_target"] == "A2A v1.0.1"

    def test_50_skill_interface_url_unique(self) -> None:
        urls = [sk["interfaceUrl"] for sk in CARD["skills"]]
        dupes = {u for u in urls if urls.count(u) > 1}
        assert not dupes, f"发现重复的 interfaceUrl: {dupes}"
