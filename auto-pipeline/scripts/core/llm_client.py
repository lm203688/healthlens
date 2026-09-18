"""
LLM 客户端：统一封装本地 Ollama + SenseNova 云端 API。

设计原则（借鉴 Karpathy autoresearch + SoL-Pi 效率层）：
- 优先 SenseNova（云端强模型，质量高）
- 兜底 Ollama minimind（本地零成本，始终可用）
- 都不可用时返回 None，调用方回退到模板/规则
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
SENSENOVA_MODEL = os.environ.get("SENSENOVA_MODEL", "sensenova-6.7-flash-lite")
SENSENOVA_KEY = os.environ.get("SENSENOVA_API_KEY", "")

# ── 场景开关（默认关闭，避免白烧推理） ──────────────────
# 实测（2026-09-18）：minimind 35B 在 10 道健康知识题上 10/10 全部被
# _is_llm_junk 拦截（复读+列表格式违规），Phase 4 相当于开着但 100%
# 回退模板——白烧每题 60-90 秒推理时间。Phase 5 审计输出全是复读建议。
# 开关保持代码通路，SenseNova 修好或换强模型时改环境变量即可启用，无需改代码。
# 启用方式：LLM_GENERATE_ENABLED=true（Phase 4 正文生成）
#          LLM_AUDIT_ENABLED=true（Phase 5 深度审计）
def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

LLM_GENERATE_ENABLED = _env_bool("LLM_GENERATE_ENABLED", False)
LLM_AUDIT_ENABLED = _env_bool("LLM_AUDIT_ENABLED", False)

# SenseNova key 从 WorkBuddy models.json 自动读取（用户记忆里的路径）
_MODELS_JSON = Path.home() / ".workbuddy" / "models.json"
if not SENSENOVA_KEY and _MODELS_JSON.exists():
    try:
        _data = json.loads(_MODELS_JSON.read_text(encoding="utf-8"))
        for _m in (_data if isinstance(_data, list) else _data.get("models", [])):
            if "sensenova" in _m.get("id", "").lower():
                SENSENOVA_KEY = _m.get("apiKey", "")
                break
    except Exception:
        pass

_ctx = ssl.create_default_context()
_WARNED: set = set()


def _warn(msg: str):
    """一次性警告，避免日志噪音"""
    if msg not in _WARNED:
        _WARNED.add(msg)
        print(f"[llm_client] WARN: {msg}")


def _call_api(url: str, payload: dict, headers: dict, timeout: int = 60) -> str | None:
    """通用 API 调用，返回 content 或 None"""
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, context=_ctx, timeout=timeout)
        d = json.loads(resp.read())
        return d["choices"][0]["message"].get("content") or ""
    except urllib.error.HTTPError as e:
        _warn(f"HTTP {e.code} from {url.split('/v1')[0]}: {e.read().decode()[:100]}")
        return None
    except Exception as e:
        _warn(f"{url.split('/v1')[0]} error: {type(e).__name__}: {e}")
        return None


def _call_sensenova(prompt: str, system: str = "", max_tokens: int = 1024,
                    temperature: float = 0.3) -> str | None:
    """调用 SenseNova 云端 API"""
    if not SENSENOVA_KEY:
        return None
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    payload = {
        "model": SENSENOVA_MODEL,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "reasoning_effort": "minimal",  # 关思考，省 token（用户记忆坑）
    }
    return _call_api(f"{SENSENOVA_URL}/chat/completions", payload,
                     {"Authorization": f"Bearer {SENSENOVA_KEY}"})


def _call_ollama(prompt: str, system: str = "", max_tokens: int = 1024,
                 temperature: float = 0.3) -> str | None:
    """调用本地 Ollama（OpenAI 兼容协议）"""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "options": {"num_predict": max_tokens},
    }
    return _call_api(f"{OLLAMA_URL}/chat/completions", payload, {})


def generate(prompt: str, system: str = "", max_tokens: int = 1024,
             temperature: float = 0.3, timeout: int = 120) -> str | None:
    """
    统一生成入口。优先 SenseNova，失败则 Ollama，都失败返回 None。

    借鉴 SoL-Pi Evidence-Preserving Reducer：失败不重试，快速降级，
    让调用方决定是回退模板还是跳过。
    """
    # 1. 尝试 SenseNova
    if SENSENOVA_KEY:
        t0 = time.time()
        result = _call_sensenova(prompt, system, max_tokens, temperature)
        if result and len(result) > 20:
            return result
        # SenseNova 失败，记日志后降级

    # 2. 兜底 Ollama
    t0 = time.time()
    result = _call_ollama(prompt, system, max_tokens, temperature)
    if result and len(result) > 20:
        return result
    return None


def generate_with_metadata(prompt: str, system: str = "", max_tokens: int = 1024,
                           temperature: float = 0.3, timeout: int = 120) -> tuple:
    """
    统一生成入口（带元数据）。返回 (content, metadata)。

    metadata 含 model / provider / latency_ms / generated_at。
    记录元数据的价值：GitHub 用户反馈里明确指出「AI 生成内容 commit 缺
    prompt / model / seed 元数据，无法追溯」（CSDN 2025-11）。这是审计
    与合规复现的基础——尤其对 FDA/FTC 2025-09 起加强执法的医疗内容。
    """
    # 1. 尝试 SenseNova
    if SENSENOVA_KEY:
        t0 = time.time()
        result = _call_sensenova(prompt, system, max_tokens, temperature)
        if result and len(result) > 20:
            return result, {
                "model": SENSENOVA_MODEL,
                "provider": "sensenova",
                "latency_ms": int((time.time() - t0) * 1000),
                "generated_at": _now_iso(),
            }

    # 2. 兜底 Ollama
    t0 = time.time()
    result = _call_ollama(prompt, system, max_tokens, temperature)
    if result and len(result) > 20:
        return result, {
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
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/models")
        resp = urllib.request.urlopen(req, context=_ctx, timeout=3)
        d = json.loads(resp.read())
        if d.get("data"):
            return True
    except Exception:
        pass
    return bool(SENSENOVA_KEY)


def is_generation_enabled() -> bool:
    """Phase 4 正文生成是否启用。默认 False（minimind 不达标，避免白烧推理）。"""
    return LLM_GENERATE_ENABLED and is_available()


def is_audit_enabled() -> bool:
    """Phase 5 深度审计是否启用。默认 False（minimind 审计建议全是复读）。"""
    return LLM_AUDIT_ENABLED and is_available()


def health_check() -> dict:
    """返回 LLM 可用性状态，供 scheduler 漏斗报告用"""
    ollama_ok = False
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/models")
        resp = urllib.request.urlopen(req, context=_ctx, timeout=3)
        d = json.loads(resp.read())
        ollama_ok = bool(d.get("data"))
    except Exception:
        pass
    return {
        "ollama": ollama_ok,
        "ollama_model": OLLAMA_MODEL,
        "sensenova": bool(SENSENOVA_KEY),
        "sensenova_model": SENSENOVA_MODEL if SENSENOVA_KEY else None,
        "any_available": ollama_ok or bool(SENSENOVA_KEY),
    }
