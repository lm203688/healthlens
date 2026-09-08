"""clinpgx_client.py — HealthLens PGx 引擎 Phase 2 实时指南数据层

借鉴开源资产:
- ClinPGx Data API (api.clinpgx.org/v1) — PharmGKB 继任 (Stanford/NIH), 无密钥, CC BY-SA 4.0
- CPIC PostgREST API (api.cpicpgx.org/v1) — gene-drug pair_view, 含 cpiclevel (A/B/C/D)

设计原则:
- 只读、无密钥、客户端自觉限速 (≤2 req/s)
- 离线 / 限流 / 解析失败 → 静默回退 (返回 None 或原样数据), 不阻断 pgx_engine 主流程
- 仅标准库 (urllib + asyncio + json + time), 零第三方依赖
- 单一网络边界 `_get_json`, 便于测试 mock
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass

CLINPGX_BASE = "https://api.clinpgx.org/v1"
CPIC_BASE = "https://api.cpicpgx.org/v1"

_HTTP_TIMEOUT = 8.0
_CACHE_TTL = 86400  # 1 天
_MIN_REQ_INTERVAL = 0.55  # ≈ ≤2 req/s 自觉限速

_last_req_ts: float = 0.0
_cache: dict[str, tuple[float, object]] = {}


def _ratelimit() -> None:
    global _last_req_ts
    wait = _MIN_REQ_INTERVAL - (time.monotonic() - _last_req_ts)
    if wait > 0:
        time.sleep(wait)


def _get_json(url: str):
    """单一网络边界: 返回解析后的 JSON, 或抛异常 (由调用方捕获并回退)。"""
    cached = _cache.get(url)
    if cached is not None:
        ts, data = cached
        if time.time() - ts < _CACHE_TTL:
            return data
    _ratelimit()
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "HealthLens-PGx/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    _cache[url] = (time.time(), data)
    return data


async def _get_json_async(url: str):
    return await asyncio.to_thread(_get_json, url)


@dataclass
class GuidelineInfo:
    gene: str
    drug: str
    cpic_level: str | None = None  # A/B/C/D
    clinpgx_level: str | None = None  # 证据等级
    guideline_name: str | None = None
    source: str = "cpic"


def get_gene_detail(gene: str) -> dict | None:
    """ClinPGx gene 详情 (名称/别名/是否有 CPIC 指南)。"""
    try:
        return _get_json(f"{CLINPGX_BASE}/data/gene/{gene}")
    except Exception:
        return None


def get_gene_drug_pairs(gene: str) -> list[dict] | None:
    """CPIC pair_view: 该基因的全部 gene-drug 对 (含指南等级)。"""
    try:
        return _get_json(f"{CPIC_BASE}/pair_view?genesymbol=eq.{gene}")
    except Exception:
        return None


def get_pair_guideline(gene: str, drug: str) -> GuidelineInfo | None:
    """查 gene-drug 对的 CPIC 指南等级。drug 做包含匹配 (容错中/英文药名)。"""
    try:
        pairs = get_gene_drug_pairs(gene) or []
    except Exception:
        return None
    drug_l = drug.lower()
    for p in pairs:
        name = (p.get("drugname") or p.get("drug") or "").lower()
        if drug_l and (drug_l in name or name in drug_l):
            return GuidelineInfo(
                gene=gene,
                drug=drug,
                cpic_level=p.get("cpiclevel"),
                clinpgx_level=p.get("clinpgxlevel"),
                guideline_name=p.get("guidelinename"),
                source="cpic",
            )
    return None


async def get_pair_guideline_async(gene: str, drug: str) -> GuidelineInfo | None:
    return await asyncio.to_thread(get_pair_guideline, gene, drug)


async def enrich_gene_drugs(gene: str, drug_recs: list[dict]) -> list[dict]:
    """给本地 PGx 用药建议附加实时 CPIC 指南等级。

    失败 (离线/限流/单条无匹配) 时该条保持原样, 不影响整体。
    注意: 本地 PGX_RULES 的 drug_name 形如 "氯吡格雷(Clopidogrel)",
    含英文子串, 可与 CPIC 的英文 drugname 做包含匹配。
    """
    if not drug_recs:
        return drug_recs
    out: list[dict] = []
    for rec in drug_recs:
        new_rec = dict(rec)
        try:
            g = await get_pair_guideline_async(gene, rec.get("drug_name", ""))
            if g is not None:
                new_rec["cpic_level"] = g.cpic_level
                new_rec["clinpgx_level"] = g.clinpgx_level
                new_rec["guideline_name"] = g.guideline_name
                new_rec["guideline_source"] = g.source
        except Exception:
            pass
        out.append(new_rec)
    return out


def demo() -> None:
    import pprint

    print("=== clinpgx_client 演示（离线/在线均可，失败回退）===")
    info = get_pair_guideline("CYP2C19", "氯吡格雷(Clopidogrel)")
    pprint.pprint(info.__dict__ if info else "（离线回退：无指南数据）")


if __name__ == "__main__":
    demo()
