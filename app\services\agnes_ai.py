"""Agnes AI API 封装 - 兼容 OpenAI 格式的异步 LLM 调用"""
import json
from typing import AsyncGenerator

import httpx
from loguru import logger

from app.config import settings

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # 秒
_TIMEOUT = 120.0  # 秒


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _build_headers() -> dict:
    """构造请求头（支持任意 OpenAI 兼容服务）"""
    api_key = settings.llm_api_key
    if not api_key:
        raise ValueError(
            "未配置 LLM 凭证：请在 .env 设置 LLM_API_KEY（可搭配 LLM_BASE_URL / LLM_MODEL，"
            "兼容 DeepSeek、通义千问、OpenAI、本地 Ollama 等）或 AGNES_API_KEY"
        )
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _endpoint() -> str:
    """当前生效的 chat/completions 端点"""
    return f"{settings.llm_base_url}/chat/completions"


# ---------------------------------------------------------------------------
# 核心：非流式调用
# ---------------------------------------------------------------------------

async def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
) -> str:
    """
    调用 Agnes AI LLM（非流式），返回完整文本。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名称，默认 agnes-v1
        temperature: 温度参数，默认 0.3

    Returns:
        LLM 生成的文本内容

    Raises:
        ValueError: API Key 未配置
        httpx.HTTPStatusError: HTTP 错误
        RuntimeError: 重试耗尽或解析失败
    """
    headers = _build_headers()
    model = model or settings.llm_model
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _endpoint(),
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"Agnes AI 调用成功 | model={model} | attempt={attempt}")
            return content

        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, IndexError) as exc:
            last_exc = exc
            logger.warning(
                f"Agnes AI 调用失败 | attempt={attempt}/{_MAX_RETRIES} | error={exc}"
            )
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(_RETRY_DELAY * attempt)

    raise RuntimeError(f"Agnes AI 调用失败，重试 {_MAX_RETRIES} 次后仍不可用: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# 核心：流式调用
# ---------------------------------------------------------------------------

async def call_llm_stream(
    system_prompt: str,
    user_prompt: str,
    model: str = "",
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """
    调用 Agnes AI LLM（流式），逐 chunk yield 文本片段。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名称
        temperature: 温度参数

    Yields:
        每个 SSE data 中解析出的文本片段
    """
    headers = _build_headers()
    model = model or settings.llm_model
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
    }

    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    _endpoint(),
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield text
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
            # 流式成功完成，直接返回
            return

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            logger.warning(
                f"Agnes AI 流式调用失败 | attempt={attempt}/{_MAX_RETRIES} | error={exc}"
            )
            if attempt < _MAX_RETRIES:
                import asyncio
                await asyncio.sleep(_RETRY_DELAY * attempt)

    raise RuntimeError(f"Agnes AI 流式调用失败，重试 {_MAX_RETRIES} 次后仍不可用: {last_exc}") from last_exc