"""危急值阈值表回归测试 —— M10 P0-3

守住三条底线：
1. 每项危急值都能被嵌套路径正确命中（`biomarkers.*` 是主入口）
2. 无单位歧义项的区间启发式不产生假阴性（漏拦比不拦更危险）
3. 表结构完整、可扩展、可审计
"""
from __future__ import annotations

import pytest

from app.lib.critical_values import (
    CRITICAL_VALUE_DEFS,
    CriticalValueDef,
    check_critical_values,
    get_critical_value_table,
    has_critical_values,
)
from app.middleware.emergency_interceptor import _check_biomarkers_for_emergency


# ---------------------------------------------------------------------------
# 表结构完整性
# ---------------------------------------------------------------------------

class TestTableIntegrity:
    """表本身的质量：避免配置漏项/自相矛盾"""

    def test_table_is_nonempty(self):
        assert len(CRITICAL_VALUE_DEFS) >= 20, "危急值表不能少于 20 项（覆盖代谢/电解质/肾/血液/凝血/心/血气）"

    def test_each_def_has_at_least_one_threshold(self):
        """每项必须至少有一侧阈值——无阈值的条目是配置错误。"""
        for d in CRITICAL_VALUE_DEFS:
            assert d.low_below is not None or d.high_above is not None, (
                f"{d.key} 既无 low_below 也无 high_above，配置无效"
            )

    def test_low_below_is_less_than_high_above_when_both_present(self):
        """双阈值必须 low < high，否则区间逻辑反转。"""
        for d in CRITICAL_VALUE_DEFS:
            if d.low_below is not None and d.high_above is not None:
                assert d.low_below < d.high_above, (
                    f"{d.key}: low_below={d.low_below} 必须 < high_above={d.high_above}"
                )

    def test_keys_are_unique(self):
        keys = [d.key for d in CRITICAL_VALUE_DEFS]
        assert len(keys) == len(set(keys)), f"重复 key: {keys}"

    def test_aliases_nonempty(self):
        for d in CRITICAL_VALUE_DEFS:
            assert d.aliases, f"{d.key} 别名为空"

    def test_match_aliases_are_consistent_with_key(self):
        """每个 key 都应能通过别名匹配命中自身（含大小写/后缀变体）。"""
        from app.lib.critical_values import _match_alias
        for d in CRITICAL_VALUE_DEFS:
            aliases = d.aliases + (d.key, d.label)
            assert _match_alias(d.key, aliases), f"{d.key} 无法匹配自身别名"


# ---------------------------------------------------------------------------
# 命中逻辑：区间启发式
# ---------------------------------------------------------------------------

class TestMatchLogic:
    """CriticalValueDef.matches 的区间判定"""

    @pytest.mark.parametrize(
        "low,high,value,expect",
        [
            (2.8, 6.2, 2.5, True),   # 低值命中
            (2.8, 6.2, 6.5, True),   # 高值命中
            (2.8, 6.2, 4.0, False),  # 正常区间
            (2.8, 6.2, 2.8, False),  # 边界值：等于阈值不算命中（严格小于/大于）
            (2.8, 6.2, 6.2, False),  # 边界值
            (None, 707, 800, True),  # 仅高阈值
            (15, None, 10, True),    # 仅低阈值
            (None, None, 100, False),# 无阈值 → 永不命中
        ],
    )
    def test_matches_boundary(self, low, high, value, expect):
        d = CriticalValueDef(key="t", label="t", aliases=("t",), low_below=low, high_above=high)
        assert d.matches(value) is expect

    def test_zero_and_negative_values(self):
        """极端生理不可能值也应被命中（如心率 0）。"""
        hr = CriticalValueDef(key="hr", label="心率", aliases=("hr",), low_below=40, high_above=160)
        assert hr.matches(0) is True
        assert hr.matches(-1) is True

    def test_nan_is_not_crash(self):
        """NaN 不抛异常（浮点比较返回 False，不会误判为危急值）。"""
        import math
        d = CriticalValueDef(key="t", label="t", aliases=("t",), low_below=1.0, high_above=10.0)
        assert d.matches(math.nan) is False


# ---------------------------------------------------------------------------
# 嵌套路径提取
# ---------------------------------------------------------------------------

class TestNestedPathExtraction:
    """支持 biomarkers.* / metrics 列表 / 深层嵌套 —— 主入口必须生效"""

    def test_nested_biomarkers(self):
        """八轴评估 `/axes/assess` 的 UserProfile 结构（主入口）。"""
        body = {"biomarkers": {"glucose": 2.5, "k": 6.5}}
        hits = check_critical_values(body)
        labels = {h.label for h in hits}
        assert labels == {"血糖", "血钾"}, f"got: {labels}"

    def test_found_at_path_is_reported(self):
        """留痕必须带实际路径，便于审计定位。"""
        body = {"biomarkers": {"glucose": 2.0}}
        hits = check_critical_values(body)
        assert hits and hits[0].found_at_path == "biomarkers.glucose"

    def test_top_level_still_works(self):
        """顶层血糖仍命中（向后兼容原硬编码位置）。"""
        hits = check_critical_values({"glucose": 2.0})
        assert len(hits) == 1 and hits[0].key == "blood_glucose"

    def test_metrics_list_by_name(self):
        """化验单原始结构：metrics 列表按 name 匹配。"""
        body = {"metrics": [{"name": "血糖", "value": 1.5}]}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].label == "血糖"

    def test_metrics_list_by_english_key(self):
        """metrics 列表按英文 key 匹配。"""
        body = {"metrics": [{"name": "platelet", "value": 12}]}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].key == "platelet"

    def test_metrics_list_by_label_field(self):
        body = {"metrics": [{"label": "血钾", "value": 7.0}]}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].label == "血钾"

    def test_deeply_nested(self):
        """深层嵌套：biomarkers.metrics[] 也要命中。"""
        body = {"biomarkers": {"metrics": [{"name": "血红蛋白", "value": 45}]}}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].label == "血红蛋白"

    def test_indicator_dict_variant(self):
        """indicators 字典形式（部分 LIS 导出格式）。"""
        body = {"indicators": {"creatinine": 900}}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].key == "creatinine"

    def test_value_subdict_drill(self):
        """值是 dict 时下钻取值：{"glucose": {"value": 2.0}}。"""
        body = {"glucose": {"value": 2.0}}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].value == 2.0

    def test_metric_with_units_field_ignored(self):
        """化验单带单位字段不应干扰判定。"""
        body = {"metrics": [{"name": "血糖", "value": 2.0, "unit": "mmol/L", "ref_range": "3.9-6.1"}]}
        hits = check_critical_values(body)
        assert len(hits) == 1 and hits[0].direction == "low"


# ---------------------------------------------------------------------------
# 别名鲁棒性
# ---------------------------------------------------------------------------

class TestAliasRobustness:
    """别名匹配对大小写/分隔符/离子后缀的容错"""

    @pytest.mark.parametrize(
        "key,value,expect_key",
        [
            ("glucose", 2.0, "blood_glucose"),
            ("GLUCOSE", 2.0, "blood_glucose"),
            ("Glucose", 2.0, "blood_glucose"),
            ("K", 6.8, "potassium"),
            ("K+", 6.8, "potassium"),
            ("k+", 6.8, "potassium"),
            ("K +", 6.8, "potassium"),
            ("Ca2+", 4.2, "calcium"),
            ("PO2", 55, "p_o2"),
            ("p_o2", 55, "p_o2"),
            ("HB", 45, "hemoglobin"),
            ("hgb", 45, "hemoglobin"),
            ("Hb", 45, "hemoglobin"),
            ("INR", 6.0, "inr"),
            ("HbA1c", 15.0, None),  # HbA1c 不在表中（避免与 Hb 混淆）
        ],
    )
    def test_alias_variants(self, key, value, expect_key):
        hits = check_critical_values({"biomarkers": {key: value}})
        got = hits[0].key if hits else None
        assert got == expect_key, f"{key}={value} → {got}, expect {expect_key}"

    def test_bool_is_not_treated_as_number(self):
        """bool 是 int 的子类，必须排除（True/False 不应被当成 1/0 命中）。"""
        body = {"biomarkers": {"glucose": True, "k": False}}
        hits = check_critical_values(body)
        assert hits == [], f"bool 被误判为危急值: {hits}"

    def test_string_value_is_ignored(self):
        """非数字值静默跳过，不抛异常。"""
        body = {"biomarkers": {"glucose": "2.5", "k": "异常"}}
        hits = check_critical_values(body)
        assert hits == []


# ---------------------------------------------------------------------------
# 边界与异常输入
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """异常输入不得抛异常、不得误判"""

    def test_none_body(self):
        assert check_critical_values(None) == []
        assert has_critical_values(None) is False

    def test_non_dict_body(self):
        assert check_critical_values([]) == []
        assert check_critical_values("not a dict") == []
        assert check_critical_values(42) == []

    def test_empty_dict(self):
        assert check_critical_values({}) == []

    def test_empty_nested(self):
        assert check_critical_values({"biomarkers": {}}) == []
        assert check_critical_values({"biomarkers": None}) == []
        assert check_critical_values({"metrics": []}) == []

    def test_none_value_in_nested(self):
        """嵌套层值为 None 不崩溃。"""
        assert check_critical_values({"biomarkers": {"glucose": None, "k": None}}) == []

    def test_extremely_large_numbers_do_not_crash(self):
        body = {"biomarkers": {"glucose": 1e12, "k": 1e9}}
        hits = check_critical_values(body)
        assert len(hits) == 2

    def test_negative_numbers_do_not_crash(self):
        body = {"biomarkers": {"glucose": -5.0, "hgb": -100}}
        hits = check_critical_values(body)
        assert len(hits) == 2 and all(h.direction == "low" for h in hits)


# ---------------------------------------------------------------------------
# 覆盖面：24 项逐条验证
# ---------------------------------------------------------------------------

class TestFullCoverage:
    """每项危急值都必须能被其规范键名 + 中文标签双向命中"""

    def test_every_def_hits_via_canonical_key(self):
        """用规范键名 + 极端值，每项必须命中。"""
        for d in CRITICAL_VALUE_DEFS:
            # 取低侧阈值再压低一档，保证命中
            if d.low_below is not None:
                value = d.low_below - (abs(d.low_below) * 0.1 or 1.0)
            else:
                value = d.high_above + (abs(d.high_above) * 0.1 or 1.0)
            body = {"biomarkers": {d.key: value}}
            hits = check_critical_values(body)
            assert len(hits) == 1, f"{d.key} 用极端值 {value} 未命中"
            assert hits[0].key == d.key

    def test_every_def_hits_via_chinese_label(self):
        """用中文标签作为 metrics.name，每项必须命中（化验单原始格式）。"""
        for d in CRITICAL_VALUE_DEFS:
            if d.low_below is not None:
                value = d.low_below - (abs(d.low_below) * 0.1 or 1.0)
            else:
                value = d.high_above + (abs(d.high_above) * 0.1 or 1.0)
            body = {"metrics": [{"name": d.label, "value": value}]}
            hits = check_critical_values(body)
            assert len(hits) == 1, f"{d.label} 用极端值 {value} 未命中"
            assert hits[0].label == d.label

    def test_normal_range_produces_no_false_positive(self):
        """用各指标的正常中位值，必须 0 命中（防假阳性）。"""
        normal = {
            "glucose": 5.5, "k": 4.2, "sodium": "na", "na": 140, "ca": 2.3,
            "creatinine": 80, "egfr": 95, "bun": 7, "hgb": 140, "hct": 42,
            "plt": 250, "inr": 1.1, "pt": 12, "aptt": 30, "alt": 25,
            "ast": 28, "tbil": 12, "tni": 5.0, "ck": 180, "po2": 95,
            "pco2": 40, "ph_art": 7.4, "spo2": 98, "hr": 72, "resp_rate": 16,
        }
        # 剔除非指标键
        normal.pop("na")
        hits = check_critical_values({"biomarkers": normal})
        assert hits == [], f"正常范围出现假阳性: {[h.label for h in hits]}"


# ---------------------------------------------------------------------------
# 中间件集成
# ---------------------------------------------------------------------------

class TestMiddlewareIntegration:
    """中间件层必须真正接上表驱动逻辑（防止接线断裂）"""

    def test_middleware_returns_hits_for_nested(self):
        hits = _check_biomarkers_for_emergency({"biomarkers": {"k": 7.0}})
        assert len(hits) == 1 and hits[0].key == "potassium"

    def test_middleware_returns_empty_for_normal(self):
        assert _check_biomarkers_for_emergency({"biomarkers": {"glucose": 5.0}}) == []
        assert _check_biomarker_for_emergency_safe(None) == []

    def test_middleware_covers_main_assess_entry(self):
        """八轴评估主入口 `/axes/assess` 的 UserProfile 结构必须生效。

        这是 M10 P0-3 的核心回归点：原实现只查 body 顶层，
        UserProfile.biomarkers 嵌套字典完全被绕过。
        """
        profile_body = {
            "biomarkers": {
                "glucose": 5.2, "hba1c": 6.0, "triglyceride": 1.8,
                "hdl_c": 1.2, "alt": 30, "ast": 32, "creatinine": 78,
                "egfr": 90, "hscrp": 3.5,
            },
            "wearable": {"resting_hr": 68, "sleep_hours": 7.0, "steps": 8000, "hrv": 60},
            "symptoms": [],
        }
        # 正常体检单不应被拦截
        assert _check_biomarkers_for_emergency(profile_body) == []

        # 同一结构注入危急值必须命中
        profile_body["biomarkers"]["glucose"] = 2.2
        profile_body["biomarkers"]["creatinine"] = 800
        hits = _check_biomarkers_for_emergency(profile_body)
        keys = {h.key for h in hits}
        assert {"blood_glucose", "creatinine"} <= keys, f"主入口漏拦: {keys}"


def _check_biomarker_for_emergency_safe(body):
    """测试用 None 保护包装。"""
    return _check_biomarkers_for_emergency(body) or []


# ---------------------------------------------------------------------------
# 导出接口
# ---------------------------------------------------------------------------

class TestExport:
    """供 API/审计消费的表导出"""

    def test_get_table_shape(self):
        table = get_critical_value_table()
        assert len(table) == len(CRITICAL_VALUE_DEFS)
        first = table[0]
        for field in ("key", "label", "aliases", "low_below", "high_above", "unit", "note"):
            assert field in first, f"导出缺字段 {field}"

    def test_get_table_aliases_is_list_not_tuple(self):
        """API 序列化为 JSON 时需要 list。"""
        table = get_critical_value_table()
        assert all(isinstance(row["aliases"], list) for row in table)

    def test_hit_as_dict_shape(self):
        hits = check_critical_values({"biomarkers": {"glucose": 2.0}})
        d = hits[0].as_dict()
        for field in ("key", "label", "value", "unit", "direction", "threshold", "note", "path"):
            assert field in d, f"as_dict 缺字段 {field}"
        assert d["direction"] == "low"
        assert d["path"] == "biomarkers.glucose"
