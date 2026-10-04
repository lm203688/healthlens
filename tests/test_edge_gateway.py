"""边缘网关云侧映射的自测（纯函数，不起 app）"""
from app.connectors.edge_gateway import LOINC_MAP, map_metrics_to_observations

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
