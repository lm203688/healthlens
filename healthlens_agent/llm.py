"""llm.py — 四角色 Agent 用的最小 LLM 客户端（P0-13）

设计（延续本仓零成本/零硬依赖原则）：
- 无第三方依赖（stdlib urllib），走 OpenAI 兼容 /chat/completions；
- 未配置 HL_TEAM_LLM_* 环境变量 → llm_enabled() 返回 False，调用方
  显式降级到规则引擎，绝不静默伪装成已用 LLM；
- 调用失败（网络/HTTP/解析）→ 抛异常，由 team.py 捕获并降级；
- 输出严格解析（可选），失败返回原字符串。

配置（OpenAI 兼容端点，SenseNova 实测可用）：
  HL_TEAM_LLM_BASE_URL = https://token.sensenova.cn/v1
  HL_TEAM_LLM_API_KEY  = <key>
  HL_TEAM_LLM_MODEL    = deepseek-v4-flash

注意：不要指向 http://150.158.119.19:8420/v1 —— 该 ATEX 网关 2026-09-08 实测
已不存在（端口无监听），历史上曾在 bias_judge.py 文档里误导过配置。

用法：
    if llm_enabled():
        text = chat("...", system="...", temperature=0)
    else:
        text = rule_based_fallback(...)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

# 与 bias_judge 一致的重试策略：SenseNova flash 级模型 TPM/RPM 限制紧，
# 429/5xx 时线性退避重试；其余 4xx（鉴权/模型名）不重试。
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.5
_TIMEOUT = 30
_RETRY_CODES = frozenset({429, 500, 502, 503, 504})


def llm_enabled() -> bool:
    """检查 HL_TEAM_LLM_* 环境变量是否齐全。未配置时团队降级到规则。"""
    return bool(os.environ.get("HL_TEAM_LLM_BASE_URL")) and bool(
        os.environ.get("HL_TEAM_LLM_MODEL")
    )


def chat(
    user: str,
    system: str = "",
    temperature: float = 0.0,
    max_tokens: int = 512,
    json_mode: bool = False,
) -> str:
    """调用 OpenAI 兼容端点做单轮 chat completion。

    Args:
        user: 用户消息
        system: 系统提示词
        temperature: 采样温度（0 = 确定性）
        max_tokens: 最大输出 token
        json_mode: 是否请求 JSON 输出（部分模型支持）

    Returns:
        模型回复的纯文本内容。

    Raises:
        RuntimeError: 端点未配置
        urllib.error.HTTPError: 非重试类 HTTP 错误
        json.JSONDecodeError: 模型返回体解析失败
    """
    if not llm_enabled():
        raise RuntimeError("HL_TEAM_LLM_* 未配置，LLM 不可用")

    base = os.environ["HL_TEAM_LLM_BASE_URL"].rstrip("/")
    model = os.environ["HL_TEAM_LLM_MODEL"]
    key = os.environ.get("HL_TEAM_LLM_API_KEY", "")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        # 部分 OpenAI 兼容端点支持 response_format，不支持的会 400 —— 用 prompt 强制
        # JSON 输出（在 system 提示词中），而不是依赖 response_format 参数。
        pass

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body, method="POST"
    )
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in _RETRY_CODES or attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(_BACKOFF_SECONDS * attempt)
    else:  # pragma: no cover
        raise last_exc if last_exc else RuntimeError("LLM 调用未产生结果")

    return data["choices"][0]["message"]["content"]


def chat_json(
    user: str,
    system: str = "",
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> dict:
    """调用 chat 并解析 JSON 返回。

    模型可能包裹在 ```json ... ``` 代码块中，做容错剥离。解析失败抛异常，
    由调用方降级到规则。
    """
    content = chat(user=user, system=system, temperature=temperature, max_tokens=max_tokens)
    content = content.strip()
    if content.startswith("```"):
        # 剥离 markdown 代码围栏
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
        content = content.strip()
    return json.loads(content)


def llm_config_dict() -> dict:
    """返回当前 LLM 配置摘要（供 team_run 输出到响应体，透明可审计）。"""
    if not llm_enabled():
        return {"enabled": False, "reason": "HL_TEAM_LLM_* 未配置"}
    return {
        "enabled": True,
        "base_url": os.environ.get("HL_TEAM_LLM_BASE_URL", ""),
        "model": os.environ.get("HL_TEAM_LLM_MODEL", ""),
    }
