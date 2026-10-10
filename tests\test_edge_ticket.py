"""边缘网关票据：签发/校验/越权/吊销。

这里测的是「身份边界」，不是 Happy Path —— 共享静态 token 之所以要换成票据，
就是因为它一旦泄露等于所有盒子全泄露，所以重点全在负值用例上。
"""
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.api import device_metrics, edge_ticket
from app.config import settings
from app.main import app

SECRET = "test-edge-ticket-secret-not-real"
GW = "hlgw-ticket"
REF = "u-ticket-1"


@pytest.fixture()
def token_mode(monkeypatch):
    """关掉静态令牌，逼所有用例都走票据路径 —— 否则票据一挂静态令牌兜底就测不到越权"""
    monkeypatch.setattr(settings, "EDGE_GATEWAY_TOKEN", "")
    monkeypatch.setattr(settings, "EDGE_TICKET_SECRET", SECRET)
    device_metrics.reset_backend()
    yield
    device_metrics.reset_backend()


def _make_ticket(monkeypatch_claims=None, ttl=3600, key=None, typ=edge_ticket.TICKET_TYPE):
    issued = edge_ticket.issue_ticket("42", GW, REF, ttl)
    return issued["token"]


def test_roundtrip_carries_bound_identity(token_mode):
    issued = edge_ticket.issue_ticket("42", GW, REF, 3600)
    claims = edge_ticket.decode_ticket(issued["token"])
    assert claims["user_ref"] == REF
    assert claims["gateway_id"] == GW
    assert claims["sub"] == "42"
    assert claims["typ"] == "edge"


def test_access_token_cannot_be_used_as_ticket(token_mode):
    """登录态 access token 和票据同算法同密钥，只靠 typ 区分；漏了这道隔离就能冒用"""
    access = jwt.encode({"sub": "42", "typ": "access"}, SECRET, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(Exception) as exc:
        edge_ticket.decode_ticket(access)
    assert exc.value.status_code == 401
    assert "不是一张边缘设备票据" in exc.value.detail


def test_foreign_key_signature_is_rejected(token_mode):
    other = jwt.encode(
        {"sub": "42", "typ": "edge", "user_ref": REF, "gateway_id": GW, "exp": 9**9},
        "someone-elses-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(Exception) as exc:
        edge_ticket.decode_ticket(other)
    assert exc.value.status_code == 401


def test_expired_ticket_is_rejected(token_mode):
    """签发层不校验过期（签发时 ttl 由用户给），过期只在 decode_ticket 拦"""
    import time

    issued = edge_ticket.issue_ticket("42", GW, REF, 3600)
    expired = jwt.encode(
        {
            "sub": "42",
            "typ": "edge",
            "user_ref": REF,
            "gateway_id": GW,
            "jti": issued["claims"]["jti"],
            "exp": int(time.time()) - 10,
            "iat": int(time.time()) - 100,
        },
        SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(Exception) as exc:
        edge_ticket.decode_ticket(expired)
    assert exc.value.status_code == 401
    assert "过期" in exc.value.detail


def test_revoked_ticket_is_rejected(token_mode, monkeypatch):
    """签名票据无状态，吊销靠 jti 失效清单 —— 清单失效就会「已吊销票据复活」"""
    issued = edge_ticket.issue_ticket("42", GW, REF, 3600)
    revoked: set = set()
    monkeypatch.setattr(edge_ticket, "_is_revoked", lambda jti: jti in revoked)
    revoked.add(issued["claims"]["jti"])
    with pytest.raises(Exception) as exc:
        edge_ticket.decode_ticket(issued["token"])
    assert exc.value.status_code == 401
    assert "吊销" in exc.value.detail


BODY = {
    "gateway_id": GW,
    "user_ref": REF,
    "day": "2026-10-04",
    "metrics": [{"key": "hl.eeg.alpha_ratio", "value": 0.4, "unit": "ratio"}],
}


def _post_ticket(client, ticket, body=None, nonce="n-ticket-0001"):
    return client.post(
        "/api/v1/device-metrics",
        json=BODY if body is None else body,
        headers={"X-HL-Edge-Ticket": ticket, "X-HL-Edge-Nonce": nonce},
    )


def test_ticket_authenticated_upload_succeeds(token_mode):
    ticket = _make_ticket()
    r = _post_ticket(_client(), ticket)
    assert r.status_code == 200, r.text
    assert r.json()["auth"] == "ticket"


def test_body_claim_mismatch_is_forbidden(token_mode):
    """拿 A 的票据把数据标成 B 的 user_ref —— 这是一条越权写入通道，必须 403"""
    ticket = _make_ticket()
    r = _post_ticket(_client(), ticket, {**BODY, "user_ref": "u-someone-else"})
    assert r.status_code == 403
    assert "不一致" in r.json()["detail"]


def test_ticket_vs_gateway_mismatch_is_forbidden(token_mode):
    ticket = _make_ticket()
    r = _post_ticket(_client(), ticket, {**BODY, "gateway_id": "hlgw-ghost"})
    assert r.status_code == 403


def test_no_credential_when_token_disabled(token_mode):
    """静态令牌关掉且无票据 → 503，而不是悄悄放行"""
    r = _post_ticket(_client(), "")
    assert r.status_code == 503


def test_ticket_replay_still_deduped(token_mode):
    ticket = _make_ticket()
    client = _client()
    assert _post_ticket(client, ticket, nonce="n-replay-0001").status_code == 200
    assert _post_ticket(client, ticket, nonce="n-replay-0001").status_code == 409


def test_ttl_bounds_are_enforced(token_mode):
    schema = edge_ticket.IssueInput
    with pytest.raises(Exception):
        schema(gateway_id=GW, user_ref=REF, ttl_seconds=5)
    with pytest.raises(Exception):
        schema(gateway_id=GW, user_ref=REF, ttl_seconds=400 * 86400)
    ok = schema(gateway_id=GW, user_ref=REF, ttl_seconds=3600)
    assert ok.ttl_seconds == 3600


def test_gateway_id_illegal_chars_rejected(token_mode):
    with pytest.raises(Exception):
        edge_ticket.IssueInput(gateway_id="hlgw; rm -rf /", user_ref=REF, ttl_seconds=3600)


def _client():
    return TestClient(app)
