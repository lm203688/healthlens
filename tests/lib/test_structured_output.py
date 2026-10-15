"""L4 structured_output 测试。

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「强制合规 JSON 输出：XGrammar」。

覆盖：
- 未装 xgrammar 时 compile_json_schema 抛 HealthLensUnavailableEngine
- probe() 结构
- enforce_json_output 提示词约束（含 schema、示例、strict 模式）
- fallback_validate 用 pydantic 校验（合法/非法/复杂 schema）
- fallback_validate_with_violations 返回明细
- Markdown 围栏剥离
- 未知 schema 类型兜底
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from app.lib.engine_exceptions import HealthLensUnavailableEngine
from app.lib.structured_output import (
    _derive_example,
    _extract_json_object,
    _strip_fences,
    compile_json_schema,
    enforce_json_output,
    fallback_validate,
    fallback_validate_with_violations,
    probe,
)


# ─────────────────────────── Fixtures ───────────────────────────

SIMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "greeting": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["greeting", "count"],
}


NESTED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        },
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["user", "tags"],
}


ENUM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["healthy", "attention", "critical"]},
    },
    "required": ["status"],
}


# ─────────────────────────── 1. xgrammar 未装 → fail-loud ───────────────────────────

class TestXGrammarUnavailable:
    """未装 xgrammar 时严格 fail-loud。"""

    def test_compile_raises_when_xgrammar_missing(self) -> None:
        import importlib.util

        has = importlib.util.find_spec("xgrammar") is not None
        if has:
            pytest.skip("xgrammar installed, cannot test missing path")
        with pytest.raises(HealthLensUnavailableEngine):
            compile_json_schema(SIMPLE_SCHEMA)

    def test_exception_has_install_hint(self) -> None:
        import importlib.util

        has = importlib.util.find_spec("xgrammar") is not None
        if has:
            pytest.skip("xgrammar installed")
        with pytest.raises(HealthLensUnavailableEngine) as exc_info:
            compile_json_schema(SIMPLE_SCHEMA)
        assert "xgrammar" in str(exc_info.value)
        assert exc_info.value.required_package == "xgrammar"

    def test_probe_returns_correct_state(self) -> None:
        import importlib.util

        expected = importlib.util.find_spec("xgrammar") is not None
        r = probe()
        assert r["engine"] == "xgrammar"
        assert r["available"] == expected
        assert "install_hint" in r
        assert "note" in r

    def test_compile_rejects_non_dict(self) -> None:
        with pytest.raises(ValueError, match="dict"):
            compile_json_schema("not a dict")  # type: ignore[arg-type]


# ─────────────────────────── 2. enforce_json_output ───────────────────────────

class TestEnforceJsonOutput:
    """提示词强约束。"""

    def test_basic_enforcement(self) -> None:
        out = enforce_json_output("请回答", SIMPLE_SCHEMA)
        assert "OUTPUT CONTRACT" in out
        assert "JSON" in out
        # 原始 prompt 应保留在开头
        assert out.startswith("请回答")

    def test_contains_schema(self) -> None:
        out = enforce_json_output("p", SIMPLE_SCHEMA)
        # schema 的关键字段应出现在输出中
        assert "greeting" in out
        assert "count" in out
        assert "required" in out

    def test_strict_false_no_contract(self) -> None:
        out = enforce_json_output("p", SIMPLE_SCHEMA, strict=False)
        assert "OUTPUT CONTRACT" not in out
        # 但 schema 也不出现在输出中（strict=False 时不追加）
        assert "greeting" not in out

    def test_with_example_included(self) -> None:
        out = enforce_json_output(
            "p", SIMPLE_SCHEMA, include_example=True, example={"greeting": "hi", "count": 1}
        )
        assert "EXAMPLE RESPONSE" in out
        assert '"greeting": "hi"' in out
        assert '"count": 1' in out

    def test_auto_derive_example(self) -> None:
        """include_example=True 但 example=None 时自动派生。"""
        out = enforce_json_output("p", SIMPLE_SCHEMA, include_example=True)
        assert "EXAMPLE RESPONSE" in out
        # 应包含一个合法示例
        assert "greeting" in out
        assert "count" in out

    def test_prompt_at_start(self) -> None:
        out = enforce_json_output("  my prompt  ", SIMPLE_SCHEMA)
        assert out.lstrip().startswith("my prompt")

    def test_strict_false_include_example(self) -> None:
        out = enforce_json_output(
            "p", SIMPLE_SCHEMA, strict=False, include_example=True, example={"greeting": "x", "count": 1}
        )
        assert "OUTPUT CONTRACT" not in out
        assert "EXAMPLE RESPONSE" in out

    def test_complex_schema_renders(self) -> None:
        out = enforce_json_output("p", NESTED_SCHEMA)
        assert "user" in out
        assert "tags" in out

    def test_enforcement_has_all_required_rules(self) -> None:
        """强约束提示词应包含 10 条核心规则。"""
        out = enforce_json_output("p", SIMPLE_SCHEMA)
        for keyword in (
            "No markdown code fences",
            "No trailing commas",
            "required fields must be present",
            "Numbers are JSON numbers",
            "Booleans are true / false",
            "Nulls are JSON null",
        ):
            assert keyword in out


# ─────────────────────────── 3. fallback_validate ───────────────────────────

class TestFallbackValidate:
    """Fallback pydantic 校验。"""

    def test_valid_simple_schema(self) -> None:
        text = '{"greeting": "hi", "count": 3}'
        assert fallback_validate(text, SIMPLE_SCHEMA) is True

    def test_missing_required_field_fails(self) -> None:
        text = '{"greeting": "hi"}'
        assert fallback_validate(text, SIMPLE_SCHEMA) is False

    def test_wrong_type_fails(self) -> None:
        text = '{"greeting": "hi", "count": "not_a_number"}'
        assert fallback_validate(text, SIMPLE_SCHEMA) is False

    def test_invalid_json_returns_false(self) -> None:
        assert fallback_validate("{not json", SIMPLE_SCHEMA) is False

    def test_trailing_comma_fails(self) -> None:
        text = '{"greeting": "hi", "count": 3,}'
        assert fallback_validate(text, SIMPLE_SCHEMA) is False

    def test_extra_fields_allowed(self) -> None:
        """pydantic 默认允许额外字段（未用 ConfigDict(extra='forbid')）。"""
        text = '{"greeting": "hi", "count": 3, "extra": "x"}'
        # 当前实现允许额外字段（保守策略）
        assert fallback_validate(text, SIMPLE_SCHEMA) is True

    def test_markdown_fence_stripped(self) -> None:
        text = '```json\n{"greeting": "hi", "count": 3}\n```'
        assert fallback_validate(text, SIMPLE_SCHEMA) is True

    def test_markdown_fence_no_lang(self) -> None:
        text = '```\n{"greeting": "hi", "count": 3}\n```'
        assert fallback_validate(text, SIMPLE_SCHEMA) is True

    def test_prose_around_json_stripped(self) -> None:
        """从噪声文本中提取 JSON。"""
        text = 'Here is the answer: {"greeting": "hi", "count": 3} Thanks!'
        assert fallback_validate(text, SIMPLE_SCHEMA) is True

    def test_nested_object(self) -> None:
        text = json.dumps({"user": {"name": "A"}, "tags": ["x", "y"]})
        assert fallback_validate(text, NESTED_SCHEMA) is True

    def test_nested_missing_required(self) -> None:
        text = json.dumps({"user": {}, "tags": []})
        assert fallback_validate(text, NESTED_SCHEMA) is False

    def test_array_validation(self) -> None:
        text = json.dumps({"user": {"name": "A"}, "tags": ["x", "y"]})
        assert fallback_validate(text, NESTED_SCHEMA) is True
        # 错误类型（tags 应为 array 但传 string）
        bad = json.dumps({"user": {"name": "A"}, "tags": "not-array"})
        assert fallback_validate(bad, NESTED_SCHEMA) is False

    def test_empty_string_fails(self) -> None:
        assert fallback_validate("", SIMPLE_SCHEMA) is False

    def test_empty_object_missing_required(self) -> None:
        assert fallback_validate("{}", SIMPLE_SCHEMA) is False

    def test_boolean_types(self) -> None:
        schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}, "required": ["flag"]}
        assert fallback_validate('{"flag": true}', schema) is True
        assert fallback_validate('{"flag": "true"}', schema) is False

    def test_null_allowed_in_nullable(self) -> None:
        schema = {
            "type": "object",
            "properties": {"v": {"type": ["string", "null"]}},
            "required": ["v"],
        }
        assert fallback_validate('{"v": null}', schema) is True
        assert fallback_validate('{"v": "x"}', schema) is True


# ─────────────────────────── 4. fallback_validate_with_violations ───────────────────────────

class TestViolationsDetail:
    """返回详细 violations。"""

    def test_valid_returns_empty_list(self) -> None:
        ok, violations = fallback_validate_with_violations(
            '{"greeting": "hi", "count": 3}', SIMPLE_SCHEMA
        )
        assert ok is True
        assert violations == []

    def test_missing_required_shows_path(self) -> None:
        ok, violations = fallback_validate_with_violations('{"greeting": "hi"}', SIMPLE_SCHEMA)
        assert ok is False
        assert len(violations) >= 1
        # 应显示字段名
        joined = " ".join(violations)
        assert "count" in joined

    def test_invalid_json_shows_parse_error(self) -> None:
        ok, violations = fallback_validate_with_violations("{not json", SIMPLE_SCHEMA)
        assert ok is False
        assert "parse error" in violations[0].lower()


# ─────────────────────────── 5. _extract_json_object / _strip_fences ───────────────────────────

class TestExtractJson:
    """JSON 抽取工具。"""

    def test_strip_markdown_with_lang(self) -> None:
        text = '```json\n{"a": 1}\n```'
        assert _strip_fences(text) == '{"a": 1}'

    def test_strip_markdown_without_lang(self) -> None:
        text = '```\n{"a": 1}\n```'
        assert _strip_fences(text) == '{"a": 1}'

    def test_no_fences_returns_stripped(self) -> None:
        text = '  {"a": 1}  '
        assert _strip_fences(text) == '{"a": 1}'

    def test_extract_json_from_noise(self) -> None:
        text = 'Here: {"a": 1} done'
        assert _extract_json_object(text) == '{"a": 1}'

    def test_extract_nested_json(self) -> None:
        text = 'x {"a": {"b": 1}} y'
        assert _extract_json_object(text) == '{"a": {"b": 1}}'


# ─────────────────────────── 6. _derive_example ───────────────────────────

class TestDeriveExample:
    """Schema → 示例对象。"""

    def test_simple_object(self) -> None:
        ex = _derive_example(SIMPLE_SCHEMA)
        assert isinstance(ex, dict)
        assert "greeting" in ex
        assert "count" in ex

    def test_string_default_empty(self) -> None:
        schema = {"type": "string"}
        assert _derive_example(schema) == ""

    def test_integer_default_zero(self) -> None:
        schema = {"type": "integer"}
        assert _derive_example(schema) == 0

    def test_boolean_default_false(self) -> None:
        schema = {"type": "boolean"}
        assert _derive_example(schema) is False

    def test_array_default_single_element(self) -> None:
        schema = {"type": "array", "items": {"type": "string"}}
        ex = _derive_example(schema)
        assert isinstance(ex, list)
        assert len(ex) == 1
        assert ex[0] == ""

    def test_enum_first_value(self) -> None:
        schema = {"type": "string", "enum": ["a", "b", "c"]}
        assert _derive_example(schema) == "a"

    def test_nested_object(self) -> None:
        ex = _derive_example(NESTED_SCHEMA)
        assert isinstance(ex, dict)
        assert "user" in ex
        assert isinstance(ex["user"], dict)

    def test_unknown_type_returns_none(self) -> None:
        schema = {"type": "weird"}
        assert _derive_example(schema) is None

    def test_no_type_returns_none(self) -> None:
        assert _derive_example({}) is None

    def test_null_type_returns_none(self) -> None:
        assert _derive_example({"type": "null"}) is None
