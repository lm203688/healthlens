"""外部参考数据库连接器 — 统一基类

与 `app.connectors.base.BaseConnector` 的区别（**不要混用**）：
  - `BaseConnector` 面向「用户健康数据同步」：OAuth2 授权、token 刷新、写入
    HealthObservation。它的产物是**用户数据**。
  - `ReferenceSource` 面向「公开科学数据库查询」：无用户授权、只读、按条目
    取数。它的产物是**公共参考知识**。

设计纪律（与项目既有的 fail-loud 原则一致）：
  1. 网络失败 / 上游 4xx / 解析失败 → 抛 `ReferenceError`，**绝不返回伪造数据**。
  2. 上游返回"查无此项"（如 PDB ID 不存在）→ 抛 `not_found`，由调用方决定
     是否降级为 404，而不是返回空对象冒充成功。
  3. 速率限制按数据源真实配额实现（NCBI 无 key 3 req/s，有 key 10 req/s）。
  4. 缓存只缓存成功结果，错误永不缓存（避免把瞬时故障固化）。

上游政策参考：
  - RCSB PDB:  data.rcsb.org / search.rcsb.org，免费、无需 key
  - PubChem:   PUG-REST，免费、无需 key；官方建议 <=5 req/s
  - NCBI BLAST: URL API，免费；无 key 3 req/s，带 tool+email 更礼貌
  - UniProt:   REST，免费、无需 key
  - AlphaFold: EBI API，免费、无需 key
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# 错误模型
# ---------------------------------------------------------------------------

#: 机器可读错误码。前端/上层据此决定提示与降级策略，不要靠字符串匹配。
ERROR_CODES = {
    "not_found": "上游明确返回查无此项",
    "rate_limited": "上游 429，重试耗尽",
    "upstream_error": "上游 5xx 或不可解析响应",
    "timeout": "请求超时",
    "network_error": "DNS/连接/TLS 失败",
    "invalid_input": "入参不合法（本地校验拦截，未发出请求）",
    "license_unavailable": "需要本地商业许可（如 Schrödinger），当前不可用",
    "not_implemented": "该数据源不支持此操作",
    "parse_error": "响应结构不符合预期",
}


class ReferenceError(Exception):
    """参考数据库查询失败。

    永远不要用 `except Exception: return {}` 吞掉它——那正是本项目历史上
    axis scorer 静默失效的成因（见 fusion_engine 的 fail-loud 改造）。
    """

    def __init__(self, code: str, source: str, detail: str = "", *, status: int | None = None):
        self.code = code if code in ERROR_CODES else "upstream_error"
        self.source = source
        self.detail = detail
        self.status = status
        super().__init__(f"[{source}] {self.code}: {detail}" if detail else f"[{source}] {self.code}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "source": self.source,
            "code": self.code,
            "detail": self.detail,
            "upstream_status": self.status,
            "message": ERROR_CODES.get(self.code, ""),
        }


# ---------------------------------------------------------------------------
# 极简 TTL 缓存（进程内）
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """进程内 TTL 缓存。

    为什么不用 Redis：参考数据的读取是「同一 PDB ID 被反复查」的形态，
    进程内缓存已能消除绝大多数重复请求；引入 Redis 会把只读连接器变成
    有状态组件，反而增加部署负担。多实例部署时各实例各自缓存，可接受。
    """

    def __init__(self, max_entries: int = 512):
        self._data: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._max = max_entries

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                self._data.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: Any, ttl: float) -> None:
        async with self._lock:
            if len(self._data) >= self._max:
                # 简单淘汰：清掉最早过期的 10%
                ordered = sorted(self._data.items(), key=lambda kv: kv[1].expires_at)
                for k, _ in ordered[: max(1, self._max // 10)]:
                    self._data.pop(k, None)
            self._data[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    def size(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# 速率限制（按数据源的最小请求间隔）
# ---------------------------------------------------------------------------

class RateLimiter:
    """串行化 + 最小间隔限流。

    比令牌桶简单，但对"官方明确写了 req/s"的场景足够且不会突发打爆上游。
    """

    def __init__(self, min_interval: float):
        self._min_interval = max(0.0, min_interval)
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

@dataclass
class SourceCapability:
    """单个数据源的能力声明，用于 /bio/sources 自描述与前端开关。"""

    source: str
    display_name: str
    base_url: str
    requires_key: bool = False
    key_present: bool = True
    operations: list[str] = field(default_factory=list)
    rate_limit: str = ""
    notes: str = ""


class ReferenceSource:
    """只读参考数据库连接器基类。"""

    SOURCE: str = "reference"
    DISPLAY_NAME: str = "Reference Source"
    BASE_URL: str = ""
    REQUIRES_KEY: bool = False
    #: 最小请求间隔（秒）。NCBI 无 key = 1/3s；PubChem 建议 1/5s。
    MIN_INTERVAL: float = 0.0
    DEFAULT_TIMEOUT: float = 30.0
    DEFAULT_TTL: float = 3600.0
    USER_AGENT: str = "HealthLens/0.33 (+https://healthlens.cc; reference-connector)"

    _shared_client: httpx.AsyncClient | None = None
    _shared_loop_id: int | None = None

    def __init__(self) -> None:
        self._limiter = RateLimiter(self.MIN_INTERVAL)
        self._cache = TTLCache()

    # -- HTTP ---------------------------------------------------------------
    async def _client(self) -> httpx.AsyncClient:
        """取共享连接池。

        必须按事件循环隔离：httpx.AsyncClient 内部持有 anyio 的 transport，
        绑定在创建它时的 loop 上。跨 loop 复用（pytest 每个用例一个 loop、
        TestClient 每次请求一个 portal）会在关闭时报
        `RuntimeError: Event loop is closed`，而且失败发生在 teardown，
        表现为「请求成功但测试崩」这种极难定位的现象。
        """
        cls = type(self)
        loop_id = id(asyncio.get_running_loop())
        if (
            cls._shared_client is None
            or cls._shared_client.is_closed
            or cls._shared_loop_id != loop_id
        ):
            cls._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.DEFAULT_TIMEOUT),
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
                follow_redirects=True,
            )
            cls._shared_loop_id = loop_id
        return cls._shared_client

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        accept: str | None = None,
        retries: int = 3,
    ) -> httpx.Response:
        """带限流与重试的请求。失败抛 ReferenceError。"""
        await self._limiter.acquire()
        client = await self._client()
        headers = {"Accept": accept} if accept else None

        last_error: ReferenceError | None = None
        for attempt in range(retries):
            try:
                resp = await client.request(
                    method, url, params=params, json=json_body, data=data, headers=headers
                )
            except httpx.TimeoutException as exc:
                last_error = ReferenceError("timeout", self.SOURCE, str(exc))
            except httpx.HTTPError as exc:
                last_error = ReferenceError("network_error", self.SOURCE, str(exc))
            else:
                if resp.status_code == 404:
                    raise ReferenceError("not_found", self.SOURCE, url, status=404)
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = ReferenceError(
                        "rate_limited" if resp.status_code == 429 else "upstream_error",
                        self.SOURCE,
                        f"HTTP {resp.status_code}",
                        status=resp.status_code,
                    )
                    # 429/5xx 退避重试：0.8s, 1.6s, 3.2s
                    await asyncio.sleep(0.8 * (2 ** attempt))
                    continue
                if resp.status_code >= 400:
                    raise ReferenceError(
                        "invalid_input", self.SOURCE, resp.text[:300], status=resp.status_code
                    )
                return resp

            await asyncio.sleep(0.5 * (2 ** attempt))

        assert last_error is not None
        raise last_error

    async def _get_json(
        self, path: str, params: dict[str, Any] | None = None, *, ttl: float | None = None
    ) -> Any:
        url = path if path.startswith("http") else f"{self.BASE_URL.rstrip('/')}{path}"
        cache_key = f"GET:{url}:{sorted((params or {}).items())}"
        if ttl is None:
            ttl = self.DEFAULT_TTL
        if ttl > 0:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        resp = await self._request("GET", url, params=params)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ReferenceError("parse_error", self.SOURCE, f"非 JSON 响应: {exc}") from exc

        if ttl > 0:
            await self._cache.set(cache_key, payload, ttl)
        return payload

    async def _post_json(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        *,
        ttl: float = 0.0,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.BASE_URL.rstrip('/')}{path}"
        cache_key = f"POST:{url}:{json_body or data}"
        if ttl > 0:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached
        resp = await self._request("POST", url, json_body=json_body, data=data)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ReferenceError("parse_error", self.SOURCE, f"非 JSON 响应: {exc}") from exc
        if ttl > 0:
            await self._cache.set(cache_key, payload, ttl)
        return payload

    # -- 自描述 -------------------------------------------------------------
    def capability(self) -> SourceCapability:
        raise NotImplementedError

    async def health(self) -> dict[str, Any]:
        """轻量连通性探针。默认实现打一个已知存在的 GET。"""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<{type(self).__name__} {self.SOURCE}>"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def first_present(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """从 RCSB/PubChem 这类深层嵌套结构里安全取第一个非空值。"""
    for k in keys:
        if isinstance(payload, dict) and k in payload and payload[k] not in (None, "", []):
            return payload[k]
    return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


async def safe_health(source: ReferenceSource) -> dict[str, Any]:
    """把 health() 的异常收敛成结构化状态，供 /bio/sources 聚合展示。"""
    started = time.monotonic()
    try:
        detail = await source.health()
        return {
            "source": source.SOURCE,
            "ok": True,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "detail": detail,
        }
    except ReferenceError as exc:
        logger.warning(f"[bio] {source.SOURCE} health failed: {exc}")
        return {
            "source": source.SOURCE,
            "ok": False,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "error": exc.to_dict(),
        }
