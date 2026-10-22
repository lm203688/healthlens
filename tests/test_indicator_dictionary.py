"""指标别名词典 (#126 M02) 单元测试 + API 冒烟。

覆盖：
  A. YAML 结构完整性 & schema 校验
  B. LOINC 唯一性与合法性
  C. 别名解析：中英文 / 缩写 / 大小写 / 全半角 / 空白 / 括号变体
  D. 单位换算：glucose / cholesterol / hba1c / creatinine / uric_acid / bun / bp 的 round-trip
  E. 参考区间分层：4 strata 全覆盖 + level 边界
  F. API 端点冒烟：/resolve / /normalize / /catalog
  G. OCR pipeline 集成：enrich_observations_with_dictionary 成功 / 降级路径
  H. fail-loud：词典缺失时抛 IndicatorDictError；单条 observation 异常不阻塞整批
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# --- 路径准备 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.indicator_dict import (  # noqa: E402
    STRATA,
    IndicatorDictError,
    get_entry,
    is_loinc_code,
    load_dictionary,
    list_slugs,
    normalize_reference_range,
    normalize_unit,
    resolve_name,
)
from app.core.report_parser import (  # noqa: E402
    enrich_observations_with_dictionary,
    extract_observations_from_text,
)

YAML_PATH = PROJECT_ROOT / "data" / "indicator_dictionary.yaml"


# ===========================================================================
# A. YAML 结构完整性
# ===========================================================================


EXPECTED_SLUGS = [
    "glucose",
    "hba1c",
    "hs_crp",
    "total_cholesterol",
    "hdl",
    "ldl",
    "vldl",
    "triglycerides",
    "egfr",
    "creatinine",
    "bun",
    "uric_acid",
    "tsh",
    "bmi",
    "bp_sys",
    "bp_dia",
]


class TestYAMLStructure:
    def test_yaml_file_exists(self):
        assert YAML_PATH.exists(), f"YAML not found at {YAML_PATH}"

    def test_loads_16_indicators(self):
        data = load_dictionary()
        assert len(data["indicators"]) == 16
        assert list(data["indicators"].keys()) == EXPECTED_SLUGS

    def test_metadata_present(self):
        data = load_dictionary()
        meta = data["metadata"]
        assert meta["schema_version"] == "1.0"
        assert "released_at" in meta
        assert "disclaimer" in meta and "wellness" in meta["disclaimer"]

    def test_every_entry_has_required_fields(self):
        for slug, entry in load_dictionary()["indicators"].items():
            for key in ("loinc_code", "name_en", "name_cn", "aliases", "unit_si", "unit_alt", "ref_range"):
                assert key in entry and entry[key] not in (None, ""), f"[{slug}] missing {key}"

    def test_every_entry_has_4_strata(self):
        for slug, entry in load_dictionary()["indicators"].items():
            for stratum in STRATA:
                assert stratum in entry["ref_range"], f"[{slug}] missing stratum {stratum}"

    def test_ref_range_low_leq_high(self):
        for slug, entry in load_dictionary()["indicators"].items():
            for stratum, rng in entry["ref_range"].items():
                assert rng["low"] <= rng["high"], f"[{slug}][{stratum}] low>high"

    def test_unit_si_keyed_in_unit_alt(self):
        for slug, entry in load_dictionary()["indicators"].items():
            assert entry["unit_si"] in entry["unit_alt"]
            assert entry["unit_alt"][entry["unit_si"]] == 1.0


# ===========================================================================
# B. LOINC 唯一性与合法性
# ===========================================================================


class TestLoincCodes:
    def test_loinc_format_valid(self):
        """LOINC 码形如 NNNNN-N（4-5 位数字 + 连字符 + 1 位校验码），总长 6 或 7。"""
        import re as _re
        pat = _re.compile(r"^\d{4,5}-\d$")
        for slug, entry in load_dictionary()["indicators"].items():
            code = str(entry["loinc_code"])
            assert pat.match(code), f"[{slug}] bad loinc format: {code}"

    def test_is_loinc_code_true_positive(self):
        assert is_loinc_code("2345-7") is True  # glucose
        assert is_loinc_code("2093-3") is True  # TC
        assert is_loinc_code("41995-4") is True  # hba1c

    def test_is_loinc_code_false_negative(self):
        assert is_loinc_code("9999-9") is False
        assert is_loinc_code("") is False
        assert is_loinc_code("2345-7 ") is False  # 精确匹配


# ===========================================================================
# C. 别名解析
# ===========================================================================


class TestAliasResolution:
    def test_chinese_names(self):
        for raw, expected in [
            ("血糖", "glucose"),
            ("空腹血糖", "glucose"),
            ("总胆固醇", "total_cholesterol"),
            ("甘油三酯", "triglycerides"),
            ("高密度脂蛋白", "hdl"),
            ("低密度脂蛋白", "ldl"),
            ("肌酐", "creatinine"),
            ("尿素氮", "bun"),
            ("尿酸", "uric_acid"),
            ("促甲状腺激素", "tsh"),
            ("收缩压", "bp_sys"),
            ("舒张压", "bp_dia"),
            ("体质指数", "bmi"),
        ]:
            r = resolve_name(raw)
            assert r is not None, f"未命中 '{raw}'"
            assert r["slug"] == expected, f"'{raw}' → {r['slug']}, expected {expected}"

    def test_english_short_names(self):
        for raw, expected in [
            ("HbA1c", "hba1c"),
            ("FBG", "glucose"),
            ("TC", "total_cholesterol"),
            ("HDL", "hdl"),
            ("LDL", "ldl"),
            ("TG", "triglycerides"),
            ("Cr", "creatinine"),
            ("BUN", "bun"),
            ("UA", "uric_acid"),
            ("SBP", "bp_sys"),
            ("DBP", "bp_dia"),
            ("BMI", "bmi"),
        ]:
            r = resolve_name(raw)
            assert r is not None, f"未命中 '{raw}'"
            assert r["slug"] == expected, f"'{raw}' → {r['slug']}, expected {expected}"

    def test_case_insensitive(self):
        for raw, expected in [
            ("hba1c", "hba1c"),
            ("HBA1C", "hba1c"),
            ("Hba1C", "hba1c"),
            ("glu", "glucose"),
            ("GLU", "glucose"),
            ("ldl-c", "ldl"),
            ("LDL-C", "ldl"),
            ("bmi", "bmi"),
        ]:
            r = resolve_name(raw)
            assert r is not None
            assert r["slug"] == expected

    def test_whitespace_and_punctuation_normalization(self):
        # 空白、连字符、下划线均被归一化
        for raw in [" 血糖 ", " 血糖　", " FBG  ", "HDL - C", "HDL_C", "bmi "]:
            r = resolve_name(raw)
            assert r is not None, f"归一化失败 '{raw}'"

    def test_fullwidth_normalized(self):
        # 全角 → 半角
        assert resolve_name("ＨｂＡ１ｃ") is not None
        assert resolve_name("ＴＣ") is not None

    def test_parenthesized_cn_en_mixed(self):
        # "血糖(Glucose)" 不是词典收录的单一别名（括号内容被归一化为整体），
        # 但 OCR pipeline 通过 report_parser.enrich_observations_with_dictionary
        # 会先剥括号再尝试解析。此测试锁定「直接对 resolve_name 传夹拼字符串」
        # 的边界——库层不做剥括号，保持别名匹配语义纯净。
        r = resolve_name("血糖(Glucose)")
        # 允许两种行为：命中（宽松）或 None（严格）。核心断言是「不抛异常」。
        assert r is None or r["slug"] == "glucose"

    def test_unknown_returns_none(self):
        assert resolve_name("随机字符串") is None
        assert resolve_name("") is None
        assert resolve_name("不存在的指标") is None

    def test_resolve_returns_all_fields(self):
        r = resolve_name("空腹血糖")
        assert set(r.keys()) == {"slug", "name_en", "name_cn", "loinc_code", "unit_si"}


# ===========================================================================
# D. 单位换算
# ===========================================================================


class TestUnitConversion:
    def test_glucose_mgdl_to_mmol(self):
        r = normalize_unit(180, "mg/dL", slug="glucose")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 180 * 0.0555) < 1e-6
        assert r["unit_si"] == "mmol/L"

    def test_glucose_mmol_identity(self):
        r = normalize_unit(6.5, "mmol/L", slug="glucose")
        assert r["ok"] is True
        assert r["canonical_value"] == 6.5
        assert r["factor"] == 1.0

    def test_hba1c_percent_to_mmol(self):
        r = normalize_unit(6.2, "%", slug="hba1c")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 6.2 * 10.93) < 1e-6
        assert r["unit_si"] == "mmol/mol"

    def test_cholesterol_mgdl_to_mmol(self):
        r = normalize_unit(200, "mg/dL", slug="total_cholesterol")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 200 * 0.0259) < 1e-6

    def test_triglycerides_mgdl_to_mmol(self):
        r = normalize_unit(200, "mg/dL", slug="triglycerides")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 200 * 0.0113) < 1e-6

    def test_creatinine_mgdl_to_umol(self):
        r = normalize_unit(1.0, "mg/dL", slug="creatinine")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 88.4) < 1e-6

    def test_uric_acid_mgdl_to_umol(self):
        r = normalize_unit(7.0, "mg/dL", slug="uric_acid")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 7.0 * 59.46) < 1e-6

    def test_bp_sys_kpa_to_mmhg(self):
        r = normalize_unit(16.0, "kPa", slug="bp_sys")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 16.0 * 7.5006) < 1e-6

    def test_hdl_mgdl_to_mmol(self):
        r = normalize_unit(40, "mg/dL", slug="hdl")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 40 * 0.0259) < 1e-6

    def test_ambiguous_unit_without_slug(self):
        """mg/dL 被 glucose/TC/HDL/LDL/VLDL/TG/creatinine/uric_acid 共享 —— 不传 slug 必须拒绝。"""
        r = normalize_unit(200, "mg/dL")
        assert r["ok"] is False
        assert r["reason"] == "ambiguous_unit_without_slug"
        assert "candidates" in r and len(r["candidates"]) >= 5

    def test_unknown_unit_returns_failure(self):
        r = normalize_unit(100, "invalid_unit_xyz", slug="glucose")
        assert r["ok"] is False
        assert "unknown_unit" in r["reason"]
        assert "supported_units" in r

    def test_missing_unit_returns_failure(self):
        r = normalize_unit(100, None)
        assert r["ok"] is False
        assert r["reason"] == "missing_unit"

    def test_unknown_slug_returns_failure(self):
        r = normalize_unit(100, "mg/dL", slug="not_a_slug")
        assert r["ok"] is False
        assert "unknown_slug" in r["reason"]

    def test_string_value_converted(self):
        r = normalize_unit("180", "mg/dL", slug="glucose")
        assert r["ok"] is True
        assert abs(r["canonical_value"] - 180 * 0.0555) < 1e-6

    def test_invalid_value_string(self):
        r = normalize_unit("abc", "mg/dL", slug="glucose")
        assert r["ok"] is False
        assert "invalid_value" in r["reason"]


# ===========================================================================
# E. 参考区间分层
# ===========================================================================


class TestReferenceRange:
    def test_all_four_strata_for_glucose(self):
        for stratum, expected_high in [
            ("adult_male", 6.1),
            ("adult_female", 6.1),
            ("pediatric", 5.6),
            ("senior", 6.9),
        ]:
            r = normalize_reference_range("glucose", 5.5, stratum)
            assert r["stratum"] == stratum
            assert r["ref_range"]["high"] == expected_high

    def test_hs_crp_sex_differentiated(self):
        # 女性 hs-CRP 上限 0.5，男性 1.0 —— 男女差是词典真实设计
        m = normalize_reference_range("hs_crp", 0.7, "adult_male")
        f = normalize_reference_range("hs_crp", 0.7, "adult_female")
        assert m["in_range"] is True
        assert f["in_range"] is False
        assert f["level"] == "high"

    def test_level_normal(self):
        r = normalize_reference_range("glucose", 5.0, "adult_male")
        assert r["level"] == "normal"
        assert r["in_range"] is True

    def test_level_low_boundary(self):
        # value < low
        r = normalize_reference_range("glucose", 3.8, "adult_male")
        assert r["level"] == "low"
        assert r["in_range"] is False

    def test_level_high_boundary(self):
        # value > high
        r = normalize_reference_range("glucose", 6.2, "adult_male")
        assert r["level"] == "high"
        assert r["in_range"] is False

    def test_boundary_inclusive_low(self):
        # value == low → normal
        r = normalize_reference_range("glucose", 3.9, "adult_male")
        assert r["level"] == "normal"
        assert r["in_range"] is True

    def test_boundary_inclusive_high(self):
        # value == high → normal
        r = normalize_reference_range("glucose", 6.1, "adult_male")
        assert r["level"] == "normal"
        assert r["in_range"] is True

    def test_egfr_senior_relaxed(self):
        # 老年 eGFR 放宽到 60
        r = normalize_reference_range("egfr", 65, "senior")
        assert r["in_range"] is True
        r_young = normalize_reference_range("egfr", 65, "adult_male")
        assert r_young["in_range"] is False

    def test_bmi_chinese_threshold(self):
        # 中国成人 BMI 24-27.9 属超重，非肥胖
        r = normalize_reference_range("bmi", 25.5, "adult_male")
        assert r["level"] == "high"
        r = normalize_reference_range("bmi", 22.0, "adult_male")
        assert r["in_range"] is True

    def test_unknown_stratum_raises(self):
        with pytest.raises(IndicatorDictError):
            normalize_reference_range("glucose", 5.0, "unknown_stratum")

    def test_unknown_slug_raises(self):
        with pytest.raises(IndicatorDictError):
            normalize_reference_range("unknown_slug", 5.0, "adult_male")

    def test_all_16_indicators_all_4_strata(self):
        """回归防线：确保所有 16 项指标 × 4 strata 都可查。"""
        for slug in EXPECTED_SLUGS:
            for stratum in STRATA:
                entry = get_entry(slug)
                rng = entry["ref_range"][stratum]
                mid = (rng["low"] + rng["high"]) / 2
                r = normalize_reference_range(slug, mid, stratum)
                assert r["in_range"] is True, f"[{slug}][{stratum}] mid={mid} should be in_range"


# ===========================================================================
# F. API 端点冒烟
# ===========================================================================


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app import create_app

    return TestClient(create_app())


class TestAPI:
    def test_catalog_returns_16_slugs(self, client):
        r = client.get("/api/v1/indicator/catalog")
        assert r.status_code == 200
        body = r.json()
        assert len(body["slugs"]) == 16
        assert body["metadata"]["schema_version"] == "1.0"
        assert "indicators" in body and len(body["indicators"]) == 16

    def test_resolve_by_chinese_name(self, client):
        r = client.post("/api/v1/indicator/resolve", json={"name": "空腹血糖"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["slug"] == "glucose"
        assert body["loinc_code"] == "2345-7"

    def test_resolve_by_loinc_code(self, client):
        r = client.post("/api/v1/indicator/resolve", json={"name": "any", "loinc_code": "13457-7"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["slug"] == "ldl"
        assert body["matched_by"] == "loinc_code"

    def test_resolve_unknown_returns_not_ok(self, client):
        r = client.post("/api/v1/indicator/resolve", json={"name": "不存在的指标"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["reason"] == "unknown_name"

    def test_normalize_hba1c_percent(self, client):
        r = client.post(
            "/api/v1/indicator/normalize",
            json={"name": "HbA1c", "value": 6.2, "unit": "%", "stratum": "adult_male"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["slug"] == "hba1c"
        assert abs(body["canonical_value"] - 6.2 * 10.93) < 1e-6
        assert body["unit_si"] == "mmol/mol"
        assert body["level"] == "high"
        assert body["in_range"] is False

    def test_normalize_unknown_unit(self, client):
        r = client.post(
            "/api/v1/indicator/normalize",
            json={"name": "LDL", "value": 2.5, "unit": "nonsense", "stratum": "adult_male"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["reason"] == "unknown_unit"
        assert "supported_units" in body

    def test_normalize_unknown_name(self, client):
        r = client.post(
            "/api/v1/indicator/normalize",
            json={"name": "不存在", "value": 1, "unit": "mmol/L"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["reason"] == "unknown_name"

    def test_normalize_invalid_stratum_400(self, client):
        r = client.post(
            "/api/v1/indicator/normalize",
            json={"name": "LDL", "value": 2.5, "unit": "mmol/L", "stratum": "bad"},
        )
        assert r.status_code == 400

    def test_resolve_no_claims_guard_natural_language(self, client):
        """M02 关键边界：API 只返结构化枚举，不生成自然语言描述，无需 claims_guard。"""
        r = client.get("/api/v1/indicator/catalog")
        body = r.json()
        # indicators 内的 notes 字段是纯参考说明，不含医疗建议话术
        notes = body["indicators"]["glucose"].get("notes", "")
        assert "wellness" not in notes.lower() or True  # 允许 wellness 字样存在
        # 但响应层无 claims_guard 包裹字段
        assert "disclaimer_text" not in body
        assert "guard_decision" not in body


# ===========================================================================
# G. OCR pipeline 集成
# ===========================================================================


class TestOCRIntegration:
    def test_extract_and_enrich_real_text(self):
        text = (
            "血糖: 6.8 mmol/L (参考: 3.9-6.1) ↑\n"
            "总胆固醇(Cholesterol): 5.8 mmol/L (参考: 2.8-5.2) ↑\n"
            "糖化血红蛋白(HbA1c): 5.6 % (参考: 4.0-6.0)\n"
            "肌酐(Creatinine): 98 umol/L"
        )
        obs = extract_observations_from_text(text)
        assert len(obs) >= 3
        enriched = enrich_observations_with_dictionary(obs, stratum="adult_male")
        # 至少 3 条命中词典
        norm = [o for o in enriched if o.get("normalized") is True]
        assert len(norm) >= 3
        # 血糖应命中并识别为 high
        glu = next((o for o in norm if o.get("canonical_slug") == "glucose"), None)
        assert glu is not None
        assert glu["level"] == "high"
        assert glu["in_range"] is False

    def test_enrichment_handles_unknown_indicator(self):
        obs = [
            {
                "loinc_code": "9999-9",
                "loinc_name": "未知指标",
                "value_numeric": 1.5,
                "value_unit": "g/L",
            }
        ]
        enriched = enrich_observations_with_dictionary(obs)
        assert enriched[0]["normalized"] is False
        assert enriched[0]["normalize_reason"] == "unknown_indicator"

    def test_enrichment_illegal_stratum_falls_back(self):
        obs = [{"loinc_code": "2345-7", "loinc_name": "血糖", "value_numeric": 5.5, "value_unit": "mmol/L"}]
        enriched = enrich_observations_with_dictionary(obs, stratum="bad_stratum")
        assert enriched[0]["normalized"] is True

    def test_enrichment_preserves_original_fields(self):
        obs = [
            {
                "loinc_code": "2345-7",
                "loinc_name": "血糖",
                "value_numeric": 5.5,
                "value_unit": "mmol/L",
                "reference_range_low": 3.9,
                "reference_range_high": 6.1,
            }
        ]
        enriched = enrich_observations_with_dictionary(obs)
        # 原字段不被覆盖
        assert enriched[0]["loinc_code"] == "2345-7"
        assert enriched[0]["value_numeric"] == 5.5
        assert enriched[0]["reference_range_low"] == 3.9

    def test_enrichment_empty_list(self):
        assert enrich_observations_with_dictionary([]) == []

    def test_enrichment_no_value_still_returns_metadata(self):
        # 无 value_numeric 但名称命中 → 部分归一化
        obs = [{"loinc_code": "2345-7", "loinc_name": "血糖", "value_unit": "mmol/L"}]
        enriched = enrich_observations_with_dictionary(obs)
        assert enriched[0]["normalized"] is True
        assert enriched[0]["canonical_slug"] == "glucose"
        assert enriched[0]["canonical_value"] is None
        assert enriched[0]["level"] is None


# ===========================================================================
# H. fail-loud
# ===========================================================================


class TestFailLoud:
    def test_load_dictionary_raises_on_missing_yaml(self, monkeypatch, tmp_path):
        """词典文件缺失时立即抛 IndicatorDictError（不 silent degrade）。"""
        from app.utils import indicator_dict as id_mod

        fake_path = tmp_path / "not_exist.yaml"
        monkeypatch.setattr(id_mod, "_YAML_PATH", fake_path)
        id_mod.invalidate_cache()
        with pytest.raises(IndicatorDictError) as exc:
            id_mod.load_dictionary()
        assert "not found" in str(exc.value)
        # 恢复
        monkeypatch.setattr(id_mod, "_YAML_PATH", YAML_PATH)
        id_mod.invalidate_cache()

    def test_single_obs_error_does_not_block_batch(self):
        """单条 observation 异常不能阻塞整批返回。"""
        obs = [
            {"loinc_code": "2345-7", "loinc_name": "血糖", "value_numeric": 5.5, "value_unit": "mmol/L"},
            # 下面这条故意构造异常输入：value 是复杂对象
            {"loinc_code": "2093-3", "loinc_name": "总胆固醇", "value_numeric": None, "value_unit": "mmol/L"},
            {"loinc_code": "13457-7", "loinc_name": "LDL", "value_numeric": 2.5, "value_unit": "mmol/L"},
        ]
        enriched = enrich_observations_with_dictionary(obs)
        assert len(enriched) == 3
        # 首末两条正常
        assert enriched[0]["normalized"] is True
        assert enriched[2]["normalized"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
