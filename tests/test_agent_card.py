"""A2A Agent Card 合规与诚实性测试（S3-1，2026-10-13）。

阻断两类问题：
1. **规范不合规**：A2A v1.0 的 8 个 REQUIRED 字段缺失 → 卡片无法被 agent 发现器使用。
2. **虚假能力声明**：skills[].interfaceUrl 指向不存在的端点，或在 capabilities 里声称
   未实现的协议操作（例如声明 A2A 任务生命周期但实际只有 MCP/REST）。
   历史上项目曾出现论文声明与代码实现不一致的情况，此处用 fail-loud 测试锁死。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "agent-card.json"

# A2A v1.0 AgentCard 的 8 个 REQUIRED 字段
# （来源：a2aproject/a2a-python SDK 的 REQUIRED 标记，SDK 会对其缺失打 WARNING）
AGENTCARD_REQUIRED = {
    "name",
    "description",
    "version",
    "supportedInterfaces",
    "capabilities",
    "defaultInputModes",
    "defaultOutputModes",
    "skills",
}

# A2A AgentSkill 的 REQUIRED 字段（id/name/description/tags）
SKILL_REQUIRED = {"id", "name", "description", "tags"}

# protocolBinding 的官方枚举值（A2A §5.3）；其他值必须是 URI 形式的自定义绑定
CANONICAL_BINDINGS = {"JSONRPC", "GRPC", "HTTP+JSON"}

CARD = json.loads(CARD_PATH.read_text(encoding="utf-8"))
PATH_TMPL = re.compile(r"\{[^/]+\}")


def _pyproject_version() -> str:
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _route_paths(client: TestClient) -> set[str]:
    """OpenAPI 路径模板集合（含 {path_param} 占位）。"""
    return set(client.get("/openapi.json").json()["paths"].keys())


def _match_template(url_path: str, templates: set[str]) -> str | None:
    """把真实路径与 OpenAPI 模板比对，路径参数按段占位。"""
    if url_path in templates:
        return url_path
    for tpl in templates:
        # 两边都按 / 切段，模板段若是 {x} 则与任意非空段匹配
        if len(url_path.split("/")) == len(tpl.split("/")) and all(
            s == t or (t.startswith("{") and t.endswith("}"))
            for s, t in zip(url_path.split("/"), tpl.split("/"))
        ):
            return tpl
    return None


def _strip_origin(url: str) -> str:
    p = urlparse(url)
    return p.path or "/"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from app import create_app

    return TestClient(create_app())


class TestCardFilePresence:
    """卡片文件本身的有效性。"""

    def test_file_exists_and_is_valid_json(self):
        assert CARD_PATH.is_file(), f"agent-card.json 不存在: {CARD_PATH}"

    def test_file_size_under_registry_limit(self):
        # Google Cloud Agent Registry 对 agent-card.json 限制 10 KB
        size = CARD_PATH.stat().st_size
        assert size < 10_240, f"agent-card.json {size}B 超过 Agent Registry 10KB 上限"


class TestRequiredFields:
    """A2A v1.0 REQUIRED 字段完整性。"""

    def test_agentcard_required_fields_present(self):
        missing = AGENTCARD_REQUIRED - set(CARD)
        assert not missing, f"缺少 A2A REQUIRED 字段: {sorted(missing)}"

    def test_required_fields_non_empty(self):
        for f in AGENTCARD_REQUIRED:
            assert CARD[f] not in (None, "", [], {}), f"REQUIRED 字段 {f} 为空值"

    def test_supported_interfaces_non_empty_and_wellformed(self):
        ifs = CARD["supportedInterfaces"]
        assert len(ifs) >= 1, "supportedInterfaces 至少需要一个接口"
        for i, iface in enumerate(ifs):
            for k in ("url", "protocolBinding", "protocolVersion"):
                assert iface.get(k), f"supportedInterfaces[{i}] 缺少 {k}"
            assert urlparse(iface["url"]).scheme in ("http", "https"), (
                f"supportedInterfaces[{i}].url 必须是绝对 URL"
            )

    def test_protocol_binding_is_canonical_or_uri(self):
        """自定义绑定必须以 URI 标识（A2A §5.8），避免两个项目定义同名但语义不同的绑定。"""
        for i, iface in enumerate(CARD["supportedInterfaces"]):
            b = iface["protocolBinding"]
            assert b in CANONICAL_BINDINGS or b.startswith("http"), (
                f"supportedInterfaces[{i}].protocolBinding={b!r} 既非官方枚举也非 URI 自定义绑定"
            )

    def test_default_modes_non_empty(self):
        assert CARD["defaultInputModes"], "defaultInputModes 不能为空"
        assert CARD["defaultOutputModes"], "defaultOutputModes 不能为空"

    def test_version_matches_pyproject_single_source(self):
        """卡片静态版本必须与 pyproject 单一真源一致（防版本漂移）。"""
        assert CARD["version"] == _pyproject_version(), (
            f"agent-card.json version={CARD['version']!r} 与 pyproject "
            f"{_pyproject_version()!r} 不一致"
        )


class TestSkills:
    """skills 字段的规范性与真实性。"""

    def test_at_least_one_skill(self):
        assert len(CARD["skills"]) >= 1, "skills 不能为空数组"

    def test_skill_required_fields(self):
        for i, sk in enumerate(CARD["skills"]):
            missing = SKILL_REQUIRED - set(sk)
            assert not missing, f"skills[{i}] ({sk.get('id')}) 缺少 {sorted(missing)}"

    def test_skill_ids_unique(self):
        ids = [sk["id"] for sk in CARD["skills"]]
        dupes = {x for x in ids if ids.count(x) > 1}
        assert not dupes, f"重复的 skill id: {dupes}"

    def test_skill_tags_non_empty(self):
        for sk in CARD["skills"]:
            assert sk["tags"], f"skills[{sk['id']}] tags 不能为空（A2A REQUIRED）"

    def test_skill_modes_valid_mime(self):
        for sk in CARD["skills"]:
            for k in ("inputModes", "outputModes"):
                for m in sk.get(k, []):
                    assert "/" in m, f"skills[{sk['id']}].{k} 含非 MIME 值: {m!r}"

    def test_security_requirements_reference_declared_schemes(self):
        """引用未声明的 securityScheme 会让客户端无法建立认证。"""
        declared = set(CARD.get("securitySchemes", {}))
        for sk in CARD["skills"]:
            for req in sk.get("securityRequirements", []):
                for scheme in req:
                    assert scheme in declared, (
                        f"skills[{sk['id']}] 引用未声明的 securityScheme: {scheme!r}"
                    )

    def test_personalized_skills_require_auth(self):
        """个性化技能必须声明认证；公开技能不应强制认证。"""
        need_auth = {
            "eight-axis-assessment",
            "bio-age",
            "causal-scenario",
            "food-therapy-recommend",
            "frequency-prescription",
        }
        public = {"health-check", "axis-meta", "axis-evidence", "causal-structure",
                  "knowledge-search", "mcp-tools"}
        by_id = {sk["id"]: sk for sk in CARD["skills"]}
        for sid in need_auth:
            sk = by_id[sid]
            assert sk.get("securityRequirements"), f"个性化技能 {sid} 未声明 securityRequirements"
        for sid in public:
            sk = by_id[sid]
            assert sk.get("securityRequirements") in (None, []), (
                f"公开技能 {sid} 不应强制认证"
            )


class TestNoFabricatedCapabilities:
    """核心诚实性断言：卡片不得声明代码里不存在的能力。"""

    def test_interface_urls_resolve_to_real_routes(self, client):
        """每个 skill 的 interfaceUrl 必须对应真实存在的路由。

        这是最关键的一条：防止在卡片里编造端点来夸大能力。
        模板路径（如 /api/v1/axes/evidence/{case_id}）按段占位匹配。
        """
        routes = _route_paths(client)
        failures = []
        for sk in CARD["skills"]:
            tpl = _match_template(_strip_origin(sk["interfaceUrl"]), routes)
            if tpl is None:
                failures.append(f"{sk['id']} -> {sk['interfaceUrl']}")
        assert not failures, (
            "以下 skill 声明的端点在 OpenAPI 中不存在（虚假能力）：\n  "
            + "\n  ".join(failures)
        )

    def test_supported_interface_origin_is_public_base_url(self, client):
        """supportedInterfaces 的 origin 必须是配置的公开域名，不能是 localhost。"""
        from app.config import settings

        expected = settings.PUBLIC_BASE_URL.rstrip("/")
        for iface in CARD["supportedInterfaces"]:
            p = urlparse(iface["url"])
            got = f"{p.scheme}://{p.netloc}".rstrip("/")
            assert p.scheme == "https", (
                f"supportedInterfaces url 必须是 https（当前 {p.scheme!r}）"
            )
            assert got == expected, (
                f"supportedInterfaces url origin={got!r} 与 PUBLIC_BASE_URL "
                f"{expected!r} 不一致"
            )

    def test_conformance_note_declares_a2a_endpoints(self):
        """v0.30.0 起 A2A JSON-RPC 端点已落地；note 必须点名 4 个已实现端点。"""
        note = CARD.get("conformanceNote", "")
        assert note, "缺少 conformanceNote：卡片必须披露 A2A 端点状态"
        # 至少一个"已实现"关键词（中英皆可）
        assert "已实现" in note or "implemented" in note.lower()
        assert "SendMessage" in note
        assert "ListTasks" in note
        assert "GetTask" in note
        assert "CancelTask" in note

    def test_real_tool_interface_declared_as_extension(self):
        """实际可编程接口（MCP JSON-RPC 2.0）必须通过 EXTENSIONS 显式声明。

        参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
        A2A v1.0.1 起能力声明 key 采用 SCREAMING_SNAKE_CASE。
        """
        exts = CARD["capabilities"].get("EXTENSIONS", [])
        assert exts, "capabilities.EXTENSIONS 不能为空：应声明实际工具协议"
        # MCP 扩展应在首位（实际可编程接口）
        ext = exts[0]
        assert "MCP" in ext["description"], "EXTENSIONS[0] 应声明 MCP 工具接口"
        assert ext.get("specs"), "EXTENSIONS[0] 应指向协议规范 URI"

    def test_capabilities_do_not_claim_unsupported_features(self):
        """HealthLens 无 SSE 流式与推送能力，不得声明。

        参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
        A2A v1.0.1 起能力声明 key 采用 SCREAMING_SNAKE_CASE。
        """
        caps = CARD["capabilities"]
        assert caps.get("STREAMING") is False, "不支持 SSE 流式，STREAMING 必须为 false"
        assert caps.get("PUSH_NOTIFICATIONS") is False, "不支持推送通知，PUSH_NOTIFICATIONS 必须为 false"
        assert caps.get("EXTENDED_AGENT_CARD") is False, "未实现扩展卡片，EXTENDED_AGENT_CARD 必须为 false"

    def test_extended_agent_card_flag_matches_capability(self):
        """supportsAuthenticatedExtendedCard 与 capabilities.EXTENDED_AGENT_CARD 必须自洽。

        顶层 supportsAuthenticatedExtendedCard 是 A2A 标准 camelCase 字段（不在 capabilities.* 下），
        保持 camelCase；只有 capabilities.* 层改为 SCREAMING_SNAKE_CASE。
        """
        assert CARD["supportsAuthenticatedExtendedCard"] is False
        assert CARD["capabilities"].get("EXTENDED_AGENT_CARD") is False


class TestDiscoveryEndpoint:
    """/.well-known/agent-card.json 发现端点（A2A 规范服务位置）。"""

    def test_served_at_well_known_path(self, client):
        resp = client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["Content-Type"]

    def test_served_version_is_injected_from_pyproject(self, client):
        """服务端必须注入 pyproject 版本，不信任卡片内的静态值。"""
        card = client.get("/.well-known/agent-card.json").json()
        assert card["version"] == _pyproject_version()
        # 同时确认注入了所有卡片内容（不是空对象）
        assert card["name"] == "HealthLens"
        assert len(card["skills"]) == len(CARD["skills"])

    def test_discovery_route_registered_in_openapi(self, client):
        assert "/.well-known/agent-card.json" in client.get("/openapi.json").json()["paths"]

    def test_no_cache_bypass_on_head(self, client):
        """HEAD 请求也应用同一处理器，不能绕过。"""
        resp = client.head("/.well-known/agent-card.json")
        assert resp.status_code == 200
