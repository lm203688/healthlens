"""
LLM 客户端：统一封装云端 SenseNova + 本地 Ollama。

2026-09-18 实测更新：
- 原默认 sensenova-6.7-flash-lite 返回 404 model route not found（模型已下线）
- 同一 key 的 deepseek-v4-flash 完全可用且健康知识题质量达标（4/4 通过
  Phase 4 的 _is_llm_junk 检查：无复读/无列表/无幻觉）
- glm-5.2 的 reasoning 会吞光 max_tokens（1100+ 字 reasoning 剩 3 字 content）
  不可用
- 加 429 指数退避（实测 3 次重试内可恢复）
- reasoning_effort: minimal 不被 SenseNova 接受（400），改用
  reasoning: {"type": "disabled"} 关闭思考

设计原则（Karpathy autoresearch + SoL-Pi 效率层）：
- 优先云端强模型（质量高、零本地成本）
- 自动降级链：deepseek-v4-flash → sensenova-6.8 → sensenova-6.7 → Ollama
- 都不可用时返回 None，调用方回退模板/规则
- 零额外依赖（只用标准库 urllib）
"""
import json
import os
import ssl
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "minimind:latest")
SENSENOVA_URL = "https://token.sensenova.cn/v1"
# 默认用 deepseek-v4-flash：实测 4/4 通过健康题质量检查（2026-09-18）
SENSENOVA_MODEL = os.environ.get("SENSENOVA_MODEL", "deepseek-v4-flash")
SENSENOVA_KEY = os.environ.get("SENSENOVA_API_KEY", "")

# SenseNova 降级链：主模型失败时依次尝试下一个。
# 顺序按可用性 + 质量排序：deepseek 最优、6.8 可能超时、6.7 已下线、
# glm-5.2 reasoning 吞 tokens 不可用（保留在最后仅用于紧急 fallback）。
SENSENOVA_FALLBACKS = (
    os.environ.get("SENSENOVA_FALLBACKS", "sensenova-6.8-flash-lite,sensenova-6.7-flash-lite")
    .split(",")
)
SENSENOVA_FALLBACKS = [m.strip() for m in SENSENOVA_FALLBACKS if m.strip()]

# ── 场景开关 ──────────────────────────────────────────
# 2026-09-18 更新：默认开启生成。deepseek-v4-flash 实测 4/4 通过健康题
# 质量检查（生物年龄/睡眠/肠道菌群/线粒体），质量达标。审计仍默认关闭——
# 判断类任务比生成类更难，需要更强模型（deepseek 可尝试但保守起见先关）。
def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


LLM_GENERATE_ENABLED = _env_bool("LLM_GENERATE_ENABLED", True)
LLM_AUDIT_ENABLED = _env_bool("LLM_AUDIT_ENABLED", False)

# SenseNova key 从 WorkBuddy models.json 自动读取
_MODELS_JSON = Path.home() / ".workbuddy" / "models.json"
if not SENSENOVA_KEY and _MODELS_JSON.exists():
    try:
        _data = json.loads(_MODELS_JSON.read_text(encoding="utf-8"))
        # 优先找 deepseek-v4-flash 的 key（SenseNova 端点托管），其次 sensenova
        for _m in (_data if isinstance(_data, list) else _data.get("models", [])):
            mid = _m.get("id", "").lower()
            if "deepseek" in mid or "sensenova" in mid:
                SENSENOVA_KEY = _m.get("apiKey", "")
                if SENSENOVA_KEY:
                    break
    except Exception:
        pass

_ctx = ssl.create_default_context()
_WARNED: set = set()
_RATE_LIMIT_BACKOFFS = 3  # 429 最多重试次数


def _warn(msg: str):
    """一次性警告，避免日志噪音"""
    if msg not in _WARNED:
        _WARNED.add(msg)
        print(f"[llm_client] WARN: {msg}")


def _call_api_once(url: str, payload: dict, headers: dict, timeout: int = 60):
    """单次 API 调用，返回 (content, error_msg)。429 由上层退避处理。"""
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, context=_ctx, timeout=timeout)
        d = json.loads(resp.read())
        return d["choices"][0]["message"].get("content") or "", None
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return None, f"HTTP {e.code}: {body}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _build_payload(model: str, prompt: str, system: str,
                  max_tokens: int, temperature: float) -> dict:
    """构建 OpenAI 兼容 payload。关 reasoning 避免吞 max_tokens（memory 记坑）。"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return {
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # reasoning_effort: minimal 不被 SenseNova 接受（400），
        # 用 reasoning: {"type": "disabled"} 关闭思考（用户 memory 记坑）。
        "reasoning": {"type": "disabled"},
    }


def _call_sensenova_model(model: str, prompt: str, system: str,
                          max_tokens: int, temperature: float,
                          timeout: int = 60) -> tuple:
    """调用指定模型的 SenseNova 端点。返回 (content, error)。含 429 退避。"""
    payload = _build_payload(model, prompt, system, max_tokens, temperature)
    url = f"{SENSENOVA_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {SENSENOVA_KEY}"}
    last_err = None
    for attempt in range(_RATE_LIMIT_BACKOFFS + 1):
        content, err = _call_api_once(url, payload, headers, timeout)
        if content and len(content) > 20:
            return content, None
        if err:
            # 429 退避：指数递增（8s / 16s / 24s）
            if "HTTP 429" in err and attempt < _RATE_LIMIT_BACKOFFS:
                time.sleep(8 * (attempt + 1))
                last_err = err
                continue
            last_err = err
        else:
            last_err = "empty content"
    return None, last_err


def _call_sensenova(prompt: str, system: str = "", max_tokens: int = 1024,
                   temperature: float = 0.3) -> tuple:
    """
    带降级链的 SenseNova 调用。返回 (content, model_used, error)。
    主模型失败时依次尝试 SENSENOVA_FALLBACKS 里的备用模型。
    """
    if not SENSENOVA_KEY:
        return None, None, "no key"
    # 主模型 + 备用模型依次尝试
    models = [SENSENOVA_MODEL] + SENSENOVA_FALLBACKS
    errors = []
    for model in models:
        content, err = _call_sensenova_model(model, prompt, system,
                                             max_tokens, temperature)
        if content:
            return content, model, None
        errors.append(f"{model}: {err}")
    return None, None, " | ".join(errors)


def _call_ollama(prompt: str, system: str = "", max_tokens: int = 1024,
                temperature: float = 0.3) -> tuple:
    """调用本地 Ollama（OpenAI 兼容协议）。返回 (content, error)。"""
    payload = _build_payload(OLLAMA_MODEL, prompt, system, max_tokens, temperature)
    content, err = _call_api_once(f"{OLLAMA_URL}/chat/completions", payload, {}, timeout=120)
    return content or None, err


def generate(prompt: str, system: str = "", max_tokens: int = 1024,
            temperature: float = 0.3, timeout: int = 120) -> str | None:
    """
    统一生成入口。优先 SenseNova（含降级链），失败则 Ollama，都失败返回 None。
    """
    if SENSENOVA_KEY:
        content, _, _ = _call_sensenova(prompt, system, max_tokens, temperature)
        if content and len(content) > 20:
            return content
    content, _ = _call_ollama(prompt, system, max_tokens, temperature)
    if content and len(content) > 20:
        return content
    return None


def generate_with_metadata(prompt: str, system: str = "", max_tokens: int = 1024,
                          temperature: float = 0.3, timeout: int = 120) -> tuple:
    """
    统一生成入口（带元数据）。返回 (content, metadata)。

    metadata 含 model / provider / latency_ms / generated_at。
    元数据价值：GitHub 用户反馈明确指出「AI 生成内容 commit 缺 prompt /
    model / seed 元数据无法追溯」（CSDN 2025-11）。是 FDA/FTC 2025-09 起
    加强执法的医疗内容审计与合规复现的基础。
    """
    # 1. 尝试 SenseNova（含降级链）
    if SENSENOVA_KEY:
        t0 = time.time()
        content, model_used, _ = _call_sensenova(prompt, system, max_tokens, temperature)
        if content and len(content) > 20:
            return content, {
                "model": model_used,
                "provider": "sensenova",
                "latency_ms": int((time.time() - t0) * 1000),
                "generated_at": _now_iso(),
            }

    # 2. 兜底 Ollama
    t0 = time.time()
    content, _ = _call_ollama(prompt, system, max_tokens, temperature)
    if content and len(content) > 20:
        return content, {
            "model": OLLAMA_MODEL,
            "provider": "ollama",
            "latency_ms": int((time.time() - t0) * 1000),
            "generated_at": _now_iso(),
        }
    return None, None


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def is_available() -> bool:
    """快速探测至少一个 LLM 可用（不考虑场景开关，纯可用性）"""
    if SENSENOVA_KEY:
        return True
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/models")
        resp = urllib.request.urlopen(req, context=_ctx, timeout=3)
        d = json.loads(resp.read())
        if d.get("data"):
            return True
    except Exception:
        pass
    return False


def is_generation_enabled() -> bool:
    """Phase 4 正文生成是否启用。默认 True（deepseek-v4-flash 质量达标）。"""
    return LLM_GENERATE_ENABLED and is_available()


def is_audit_enabled() -> bool:
    """Phase 5 深度审计是否启用。默认 False（保守：判断类任务需更强模型）。"""
    return LLM_AUDIT_ENABLED and is_available()


def health_check() -> dict:
    """返回 LLM 可用性状态，供 scheduler 漏斗报告用"""
    ollama_ok = False
    ollama_models = []
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/models")
        resp = urllib.request.urlopen(req, context=_ctx, timeout=3)
        d = json.loads(resp.read())
        ollama_models = [m.get("id", "") for m in d.get("data", [])]
        ollama_ok = bool(ollama_models)
    except Exception:
        pass
    return {
        "sensenova_key_available": bool(SENSENOVA_KEY),
        "sensenova_model": SENSENOVA_MODEL,
        "sensenova_fallbacks": SENSENOVA_FALLBACKS,
        "ollama": ollama_ok,
        "ollama_model": OLLAMA_MODEL,
        "ollama_models": ollama_models[:5],
        "any_available": bool(SENSENOVA_KEY) or ollama_ok,
        "generate_enabled": LLM_GENERATE_ENABLED,
        "audit_enabled": LLM_AUDIT_ENABLED,
    }
