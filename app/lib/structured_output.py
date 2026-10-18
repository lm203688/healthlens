"""结构化输出（Structured Output）—— L4 评估层

报告出处：《HealthLens_下一阶段愿景与跃迁方案_2026-10-15》§5 L4。
> 「强制合规 JSON 输出：XGrammar 0.2.8（Apache-2.0，vLLM/SGLang 默认后端）」。

定位：
- **Adapter 层**：XGrammar 是可选依赖（`[project.optional-dependencies].evaluation`），
  未装时抛 `HealthLensUnavailableEngine`（来自 L1 的 engine_exceptions.py），
  让上层明确告知「该能力不可用，需装 .[evaluation]」——绝不静默降级。
- **Fallback 后处理**：`fallback_validate(text, schema)` 用 pydantic 做后置校验，
  即使没有 XGrammar 的强制解码也能保证输出契约。
- **提示词约束**：`enforce_json_output(prompt, schema)` 追加强约束提示词，
  让 LLM 在**没有** grammar 强制解码时也更可能产出合法 JSON。

Wellness 平台术语纪律：本模块只做输出格式约束，不做业务判断。

作者：HealthLens L4 评估团队
版本：v1 (2026-10-16)
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.lib.engine_exceptions import HealthLensUnavailableEngine


# ─────────────────────────── XGrammar 探测 ───────────────────────────

# XGrammar 通过 `xgrammar` pip 包提供；探测但不静默导入。
def _xgrammar_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("xgrammar") is not None


_ENGINE_NAME = "xgrammar"
_REQUIRED_PACKAGE = "xgrammar"
_EXTRA_HINT = "evaluation"


def _require_xgrammar():
    """需要 xgrammar 时用；未装直接抛 HealthLensUnavailableEngine。"""
    if not _xgrammar_available():
        raise HealthLensUnavailableEngine(
            engine_name=_ENGINE_NAME,
            required_package=_REQUIRED_PACKAGE,
            extra_hint=_EXTRA_HINT,
            detail="pip install -e '.[evaluation]' 以安装 xgrammar>=0.2",
        )
    import xgrammar  # type: ignore[import-not-found]

    return xgrammar


# ─────────────────────────── Schema → Grammar ───────────────────────────

def compile_json_schema(schema: dict[str, Any], grammar: Any = None) -> Any:
    """把 JSON Schema 编译为 XGrammar grammar 对象（用于 LLM 解码强制约束）。

    Args:
        schema: JSON Schema 字典（draft 2020-12 或 OpenAI function-calling 风格）
        grammar: 可选的 Grammar 对象（预编译，供复用）；None 时每次编译

    Returns:
        xgrammar.Grammar 对象；未装 xgrammar 时抛 HealthLensUnavailableEngine。

    Raises:
        HealthLensUnavailableEngine: xgrammar 未安装
        ValueError: schema 不是 dict
    """
    # 先做参数校验（避免 xgrammar 缺失时掩盖 schema 类型错误）
    if not isinstance(schema, dict):
        raise ValueError(f"schema must be dict, got {type(schema).__name__}")
    if grammar is not None:
        return grammar
    _require_xgrammar()

    import xgrammar  # type: ignore[import-not-found]

    try:
        return xgrammar.CompiledGrammar.from_json_schema(json.dumps(schema, ensure_ascii=False))
    except AttributeError:
        # 不同版本 API 名不同（CompiledGrammar vs Grammar）
        return xgrammar.Grammar(json.dumps(schema, ensure_ascii=False))


# ─────────────────────────── 提示词约束 ───────────────────────────

_JSON_ONLY_INSTRUCTION = """
=== OUTPUT CONTRACT (STRICT) ===
You MUST respond with a single valid JSON object. Follow these rules exactly:
1. No markdown code fences (no ```json), no explanatory prose.
2. No trailing commas; use double quotes for keys and string values.
3. Escape all control characters and quotes inside strings.
4. Match the schema below EXACTLY — required fields must be present,
   unknown fields are forbidden.
5. Numbers are JSON numbers, not strings.
6. Booleans are true / false (not "true"/"false").
7. Nulls are JSON null (not "null").
8. Output length must be minimal but complete.
9. If uncertain about a field, use null (if nullable) or the schema default;
   NEVER invent values.
10. Do not add "reasoning", "thought", or "explanation" fields unless the
    schema declares them.

SCHEMA (JSON Schema draft 2020-12):
```json
{schema_json}
```
""".strip()


def _schema_to_compact_json(schema: dict[str, Any]) -> str:
    """把 schema 转成紧凑 JSON 字符串（缩进 2 便于 LLM 阅读）。"""
    return json.dumps(schema, ensure_ascii=False, indent=2)


def enforce_json_output(
    prompt: str,
    schema: dict[str, Any],
    *,
    strict: bool = True,
    include_example: bool = False,
    example: Any = None,
) -> str:
    """在 prompt 后追加 JSON 强约束提示词。

    Args:
        prompt: 原始提示词
        schema: JSON Schema
        strict: True 时追加"必须严格 JSON"指令（默认 True）
        include_example: 是否追加一个示例（帮助 LLM 对齐格式）
        example: 示例对象（include_example=True 时使用；None 时自动生成）

    Returns:
        拼接后的完整 prompt 字符串
    """
    parts = [prompt.rstrip()]
    if strict:
        parts.append(_JSON_ONLY_INSTRUCTION.format(schema_json=_schema_to_compact_json(schema)))
    if include_example:
        if example is None:
            example = _derive_example(schema)
        parts.append(
            "EXAMPLE RESPONSE (format only, do NOT copy values):\n"
            + json.dumps(example, ensure_ascii=False, indent=2)
        )
    return "\n\n".join(parts)


def _derive_example(schema: dict[str, Any]) -> Any:
    """从 schema 自动派生一个最小合法示例（便于 LLM 对齐格式）。

    只处理常用类型：object/properties/required/enum/number/string/boolean。
    不支持 $ref、allOf/oneOf——遇到直接跳过，避免误导 LLM。
    """
    t = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0] if schema["enum"] else None
    if t == "object" or "properties" in schema:
        out: dict[str, Any] = {}
        for prop, sub in schema.get("properties", {}).items():
            out[prop] = _derive_example(sub)
        return out
    if t == "array":
        items = schema.get("items", {})
        return [_derive_example(items)]
    if t == "string":
        return ""
    if t in ("integer", "number"):
        return 0
    if t == "boolean":
        return False
    if t == "null":
        return None
    return None  # 未知类型兜底


# ─────────────────────────── Fallback 后置校验 ───────────────────────────

_LLM_JSON_PATTERN = re.compile(r"\{[\s\S]*\}")


def _strip_fences(text: str) -> str:
    """剥离 LLM 常见 markdown 围栏（```json ... ```）。"""
    text = text.strip()
    # 尝试提取 ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        return m.group(1).strip()
    return text


def _extract_json_object(text: str) -> str:
    """从文本中抽取第一个 JSON object（可能前后有噪声）。"""
    text = _strip_fences(text)
    m = _LLM_JSON_PATTERN.search(text)
    if m:
        return m.group(0)
    return text


def _schema_to_pydantic_model(schema: dict[str, Any], name: str = "Output") -> Any:
    """把简单 JSON Schema 转成 pydantic BaseModel。

    支持：object/properties/required/enum/type/anyOf(default)/nullable。
    不支持 $ref/allOf/oneOf——遇到直接跳过该字段（保守）。

    用途：`fallback_validate` 里的后置校验（没有 XGrammar 强制解码时兜底）。
    """
    from pydantic import BaseModel, ConfigDict

    from typing import Optional

    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    annotations: dict[str, Any] = {}
    defaults: dict[str, Any] = {}

    def _py_type(sub: dict[str, Any]) -> Any:
        t = sub.get("type")
        if isinstance(t, list):
            # ["string", "null"] 视为 nullable
            types = [x for x in t if x != "null"]
            nullable = "null" in t
            if len(types) == 1:
                base = _py_type({"type": types[0], **{k: v for k, v in sub.items() if k != "type"}})
                return Optional[base] if nullable else base
            return Any
        if t == "string":
            if "enum" in sub:
                return str  # 保留 str，enum 校验通过 Field 表达
            return str
        if t == "integer":
            return int
        if t == "number":
            return float
        if t == "boolean":
            return bool
        if t == "array":
            item_t = _py_type(sub.get("items", {})) if isinstance(sub.get("items"), dict) else Any
            return list[item_t]
        if t == "object":
            # 递归构造子 model
            sub_name = f"{name}_Sub"
            return _schema_to_pydantic_model(sub, sub_name)
        if t == "null":
            return None
        return Any

    for prop, sub in props.items():
        base_t = _py_type(sub)
        if prop not in required:
            # 可选字段：Optional + default None
            annotations[prop] = Optional[base_t]
            defaults[prop] = sub.get("default", None)
        else:
            annotations[prop] = base_t
            if "default" in sub:
                defaults[prop] = sub["default"]

    ns: dict[str, Any] = {"__annotations__": annotations, "model_config": ConfigDict(strict=True)}
    for k, v in defaults.items():
        ns[k] = v

    return type(name, (BaseModel,), ns)


def _validate_with_pydantic(text: str, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """用 pydantic 做后置校验。

    Returns:
        (is_valid, violations)：is_valid=True 时 violations=[]
    """
    from pydantic import ValidationError

    # 1. 尝试解析 JSON
    json_text = _extract_json_object(text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        return False, [f"JSON parse error: {exc.msg} at position {exc.pos}"]

    # 2. 转 pydantic model 并校验
    try:
        model_cls = _schema_to_pydantic_model(schema)
    except Exception as exc:  # noqa: BLE001
        # schema 太复杂无法转换时返回 True（保守放行，不做假 negative）
        return True, [f"[warn] schema too complex for fallback: {exc}"]

    try:
        model_cls.model_validate(parsed)
        return True, []
    except ValidationError as exc:
        violations = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return False, violations


def fallback_validate(text: str, schema: dict[str, Any]) -> bool:
    """Fallback 校验：用 pydantic 后置校验 LLM 输出。

    用于没有 XGrammar 强制解码时的兜底。返回 True 表示输出合法。
    """
    ok, _ = _validate_with_pydantic(text, schema)
    return ok


def fallback_validate_with_violations(text: str, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """同 fallback_validate，但返回 violations 明细。"""
    return _validate_with_pydantic(text, schema)


# ─────────────────────────── 能力探测 ───────────────────────────

def probe() -> dict[str, Any]:
    """探测 XGrammar 是否可用（供 API /probe 端点使用）。"""
    avail = _xgrammar_available()
    if avail:
        try:
            import xgrammar  # type: ignore[import-not-found]

            version = getattr(xgrammar, "__version__", None)
        except Exception:  # noqa: BLE001
            version = None
    else:
        version = None
    return {
        "engine": _ENGINE_NAME,
        "available": avail,
        "version": version,
        "install_hint": "pip install -e '.[evaluation]'",
        "note": (
            "强制 JSON 解码（grammar-guided decoding）"
            if avail
            else "XGrammar 未装，将使用 fallback_validate 后置校验"
        ),
    }


__all__ = [
    "compile_json_schema",
    "enforce_json_output",
    "fallback_validate",
    "fallback_validate_with_violations",
    "probe",
    "HealthLensUnavailableEngine",
]
