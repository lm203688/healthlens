"""边缘网关云侧：映射逻辑 + 接收口的校验行为"""
import pytest
from fastapi.testclient import TestClient

from app.api import device_metrics
from app.config import settings
from app.connectors.edge_gateway import LOINC_MAP, map_metrics_to_observations
from app.main import app

PAYLOAD = {
    "gateway_id": "hlgw-test",
    "user_ref": "u-1",
    "day": "2026-10-04",
    "device": {"type": "muse_lsl", "label": "InteraXon Muse (muse-lsl)"},
    "metrics": [
        {"key": "hl.eeg.alpha_ratio", "value": 0.42, "unit": "ratio"},
        {"key": "hl.eeg.alpha_asymmetry", "value": 0.11, "unit": "log-ratio"},
        {"key": "resting_heart_rate", "value": 62.0, "unit": "bpm"},
    ],
}


def test_hl_namespaced_metrics_get_no_fake_loinc():
    observations = map_metrics_to_observations(PAYLOAD)
    alpha = next(o for o in observations if o["loinc_name"].endswith("hl.eeg.alpha_ratio"))
    assert alpha["loinc_code"] is None
    assert alpha["source"] == "edge_gateway:hlgw-test"
    assert alpha["recorded_at"].startswith("2026-10-04")
    assert alpha["evidence"] == "edge-derived"


def test_known_loinc_mapping_applies():
    observations = map_metrics_to_observations(PAYLOAD)
    heart = next(o for o in observations if o["loinc_code"] == "8867-4")
    assert heart["loinc_name"] == "心率"
    assert "resting_heart_rate" in LOINC_MAP


def test_out_of_physio_bounds_is_dropped():
    payload = {**PAYLOAD, "metrics": [{"key": "resting_heart_rate", "value": 900.0}]}
    assert map_metrics_to_observations(payload) == []


def test_non_numeric_value_is_skipped():
    payload = {**PAYLOAD, "metrics": [{"key": "hl.eeg.alpha_ratio", "value": "abc"}]}
    assert map_metrics_to_observations(payload) == []


def test_bad_day_falls_back_to_now():
    payload = {**PAYLOAD, "day": "not-a-day"}
    observations = map_metrics_to_observations(payload)
    assert len(observations) == 3
    assert observations[0]["recorded_at"] != "not-a-day"


def test_empty_metrics_is_fine():
    assert map_metrics_to_observations({"day": "2026-10-04", "metrics": []}) == []


def test_edge_metric_key_whitelist_pattern():
    import re

    pattern = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
    assert pattern.match("hl.eeg.alpha_ratio")
    assert not pattern.match("HL.Eeg")  # 大小写不收
    assert not pattern.match("../../etc/passwd")
    assert not pattern.match("a;b")


# ---------------------------------------------------------------- 接收口（HTTP）

BODY = {
    "gateway_id": "hlgw-test",
    "user_ref": "u-1",
    "day": "2026-10-04",
    "metrics": [{"key": "hl.eeg.alpha_ratio", "value": 0.4, "unit": "ratio"}],
}


@pytest.fixture()
def edge_client(monkeypatch):
    monkeypatch.setattr(settings, "EDGE_GATEWAY_TOKEN", "test-edge-token")
    device_metrics.reset_backend()  # 每个用例都从干净后端开始
    client = TestClient(app)
    yield client
    device_metrics.reset_backend()


def _post(client, nonce, body=None):
    return client.post(
        "/api/v1/device-metrics",
        json=BODY if body is None else body,
        headers={"X-HL-Edge-Token": "test-edge-token", "X-HL-Edge-Nonce": nonce},
    )


def test_valid_payload_accepted(edge_client):
    r = _post(edge_client, "n-valid-0001")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["metrics"] == 1
    assert "dedup_backend" in r.json()  # 降级时要能被监控发现


def test_same_nonce_replay_is_rejected(edge_client):
    assert _post(edge_client, "n-fixed-0001").status_code == 200
    assert _post(edge_client, "n-fixed-0001").status_code == 409


def test_day_injection_returns_400_not_422(edge_client):
    """day 必须走「格式非法」的 400，不能被 pydantic 长度先截成 422"""
    r = _post(edge_client, "n-dayinj-0001", {**BODY, "day": "2026-10-04; rm -rf /"})
    assert r.status_code == 400
    assert "day 格式非法" in r.json()["detail"]


def test_shape_ok_but_impossible_date_returns_400(edge_client):
    r = _post(edge_client, "n-dayreal-0001", {**BODY, "day": "2026-02-31"})
    assert r.status_code == 400
    assert "有效日期" in r.json()["detail"]


def test_user_ref_wildcard_rejected(edge_client):
    """user_ref 会拼进 Redis key，'a*' 会污染 scan 前缀导致越权命中别的 ref"""
    r = _post(edge_client, "n-refwild-0001", {**BODY, "user_ref": "a*"})
    assert r.status_code == 422


def test_bad_metric_key_returns_422(edge_client):
    r = _post(edge_client, "n-badkey-0001", {**BODY, "metrics": [{"key": "hl.eeg.bad$;rm", "value": 1.0}]})
    assert r.status_code == 422


def test_metrics_are_readable_back(edge_client):
    _post(edge_client, "n-readback-1")
    r = edge_client.get(
        "/api/v1/device-metrics",
        params={"user_ref": "u-1", "days": 3},
        headers={"X-HL-Edge-Token": "test-edge-token"},
    )
    assert r.status_code == 200
    assert r.json()["items"][0]["metrics"][0]["key"] == "hl.eeg.alpha_ratio"


def test_nonce_backend_is_cross_process_ready(monkeypatch):
    """去重必须能跨进程：Redis 后端用 SET NX 原子抢，内存降级也要对同一 nonce 只放行一次"""
    backend = device_metrics._StateBackend("redis://127.0.0.1:1/0")  # 连不上 → 降级
    assert backend.backend == "memory"
    assert backend.claim_nonce("n-xproc-1", 60) is True
    assert backend.claim_nonce("n-xproc-1", 60) is False
