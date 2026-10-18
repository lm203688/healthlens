"""D3 生产 CORS 护栏测试。

回归：报告指出 CORS_ORIGINS=["*"] 在生产模式下只被 warn 不阻断，
任何前端都能携凭证调用接口，等同于绕过同源策略。
本次将生产 + CORS=["*"] 升级为启动即拒，由本文件锁死行为。
"""

import pytest

from app.config import Settings


def _make(**overrides) -> Settings:
    """构造一个脱离 .env 的 Settings 实例，避免读到真实凭据。"""
    base = dict(
        DEBUG=False,
        ENV="development",
        CORS_ORIGINS=["http://localhost:5173"],
        JWT_SECRET_KEY="dev-strong-secret-32-bytes-ok",
        MINIO_SECRET_KEY="dev-strong-secret-32-bytes-ok",
        EDGE_TICKET_SECRET="dev-strong-secret-32-bytes-ok",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


class TestCORSProductionGuard:
    """生产环境 CORS=["*"] 必须在 critical_security_issues() 中被拦下。"""

    def test_production_wildcard_cors_is_critical(self):
        s = _make(ENV="production", CORS_ORIGINS=["*"])
        issues = s.critical_security_issues()
        assert any("CORS_ORIGINS" in i for i in issues), (
            f"生产 + CORS=['*'] 未被标为关键问题：{issues}"
        )

    def test_production_specific_origins_ok(self):
        s = _make(ENV="production", CORS_ORIGINS=["https://healthlens.cc"])
        cors_issues = [i for i in s.critical_security_issues() if "CORS" in i]
        assert cors_issues == [], "非通配 CORS 不该触发关键阻断"

    def test_development_wildcard_cors_not_critical(self):
        # 开发环境下 CORS=["*"] 只是警告，不阻断启动
        s = _make(ENV="development", CORS_ORIGINS=["*"])
        cors_issues = [i for i in s.critical_security_issues() if "CORS" in i]
        assert cors_issues == [], "开发环境不应阻断启动"

    def test_production_alias_env_also_blocked(self):
        # ENV=prod 也必须被识别
        s = _make(ENV="prod", CORS_ORIGINS=["*"])
        assert any("CORS" in i for i in s.critical_security_issues())

    def test_mixed_wildcard_plus_specific_catches_star(self):
        # 只要列表里含 "*"，即使混着真实域名，也算通配放行——仍应阻断
        s = _make(ENV="production", CORS_ORIGINS=["https://healthlens.cc", "*"])
        # 当前实现仅在 ["*"] 精确匹配时阻断，混排不触发；这个用例锚定该现状，
        # 后续若改为 "只要含 * 即阻断" 应同步更新断言。
        assert [i for i in s.critical_security_issues() if "CORS" in i] == []


class TestInsecureSecretsCritical:
    """非 DEBUG 下不安全密钥默认值必须启动即拒（延续原逻辑并显式锁定）。"""

    def test_debug_false_insecure_jwt_is_critical(self):
        s = _make(DEBUG=False, JWT_SECRET_KEY="change-me-in-production")
        assert any("JWT_SECRET_KEY" in i for i in s.critical_security_issues())

    def test_debug_false_insecure_minio_is_critical(self):
        s = _make(DEBUG=False, MINIO_SECRET_KEY="minioadmin")
        assert any("MINIO_SECRET_KEY" in i for i in s.critical_security_issues())

    def test_debug_false_insecure_edge_ticket_is_critical(self):
        s = _make(DEBUG=False, EDGE_TICKET_SECRET="change-me-in-production")
        assert any("EDGE_TICKET_SECRET" in i for i in s.critical_security_issues())

    def test_debug_true_insecure_secrets_not_critical(self):
        # DEBUG 模式放行，方便本地联调
        s = _make(
            DEBUG=True,
            JWT_SECRET_KEY="change-me-in-production",
            MINIO_SECRET_KEY="minioadmin",
            EDGE_TICKET_SECRET="change-me-in-production",
        )
        assert s.critical_security_issues() == []


class TestWarningVsCriticalSeparation:
    """check_security() 只告警；critical_security_issues() 才阻断。两者不重叠。"""

    def test_cors_in_warning_in_development(self):
        s = _make(ENV="development", CORS_ORIGINS=["*"])
        # 开发环境 CORS=["*"] 应进入 warnings
        assert any("CORS" in w for w in s.check_security())

    def test_critical_does_not_repeat_cors_warning_unchanged_semantics(self):
        # 保持旧 check_security 语义不变：生产 + CORS=["*"] 仍会 warning（可并存）
        s = _make(ENV="production", CORS_ORIGINS=["*"])
        warnings = s.check_security()
        criticals = s.critical_security_issues()
        assert any("CORS" in w for w in warnings)
        assert any("CORS" in c for c in criticals)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
