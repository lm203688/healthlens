"""专业生物数据库适配器 - UniProt / ClinVar / KEGG / STRING 异步查询"""
import asyncio
import time
from typing import Any

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# 内存缓存（TTL 24 小时，上限 500 条，LRU 驱逐）
# ---------------------------------------------------------------------------

_CACHE_TTL = 24 * 60 * 60  # 86400 秒
_CACHE_MAX = 500
_cache: dict[str, tuple[float, Any]] = {}
_last_request_time: dict[str, float] = {}  # 限流：记录上次请求时间


def _get_cached(key: str) -> Any | None:
    """从内存缓存获取，过期返回 None。超上限时驱逐最早条目。"""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL:
        _cache.pop(key, None)
        return None
    return value


def _set_cached(key: str, value: Any) -> None:
    """写入内存缓存，超上限时驱逐最早条目。"""
    if len(_cache) >= _CACHE_MAX:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest_key, None)
    _cache[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# 通用限流：每个域最多每秒 3 次请求（NCBI/KEGG 推荐）
# ---------------------------------------------------------------------------

_RATE_LIMIT = 0.35  # 最小间隔秒数（~3 req/s）


async def _rate_limit(domain: str) -> None:
    """对指定域执行限流等待"""
    last = _last_request_time.get(domain, 0)
    elapsed = time.time() - last
    if elapsed < _RATE_LIMIT:
        await asyncio.sleep(_RATE_LIMIT - elapsed)
    _last_request_time[domain] = time.time()


# ---------------------------------------------------------------------------
# 通用请求
# ---------------------------------------------------------------------------

_TIMEOUT = 30.0


async def _safe_get(url: str, headers: dict | None = None, params: dict | None = None) -> dict | list | None:
    """安全的 GET 请求，失败返回 None 并记录日志"""
    from urllib.parse import urlparse

    domain = urlparse(url).hostname or ""
    await _rate_limit(domain)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                return resp.json()
            try:
                return resp.json()
            except Exception:
                return {"raw_text": resp.text}

    except httpx.HTTPStatusError as exc:
        logger.warning(f"Bio DB HTTP 错误 | url={url} | status={exc.response.status_code}")
    except httpx.RequestError as exc:
        logger.warning(f"Bio DB 请求失败 | url={url} | error={exc}")
    except Exception as exc:
        logger.error(f"Bio DB 未知错误 | url={url} | error={exc}")
    return None


# ---------------------------------------------------------------------------
# UniProt
# ---------------------------------------------------------------------------

UNIPROT_BASE = "https://rest.uniprot.org/uniprotkb"


async def fetch_uniprot(uniprot_id: str) -> dict | None:
    """
    通过 UniProt ID 获取蛋白功能注释。

    Args:
        uniprot_id: UniProt accession，如 "P04637"

    Returns:
        解析后的蛋白注释字典，失败返回 None
    """
    cache_key = f"uniprot:{uniprot_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{UNIPROT_BASE}/{uniprot_id}.json"
    data = await _safe_get(url)

    if data is None:
        return None

    # 提取关键字段
    result = {
        "uniprot_id": uniprot_id,
        "protein_name": _extract_uniprot_name(data),
        "function": _extract_uniprot_function(data),
        "gene_symbol": _extract_uniprot_gene(data),
        "pathways": _extract_uniprot_pathways(data),
        "subcellular_location": _extract_uniprot_location(data),
    }

    _set_cached(cache_key, result)
    return result


async def fetch_uniprot_by_gene(gene_symbol: str, species: int = 9606) -> str | None:
    """
    通过基因符号解析 UniProt accession（P0-2：解除 L2 对用户输入 uniprot_id 的依赖）。

    Args:
        gene_symbol: 基因符号，如 "TP53"
        species: 物种 ID，默认 9606（人类）

    Returns:
        首个匹配的 UniProt accession 字符串；未找到返回 None。
    """
    if not gene_symbol:
        return None
    cache_key = f"uniprot_gene:{gene_symbol}:{species}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    query = f"gene:{gene_symbol} AND organism_id:{species}"
    params = {"query": query, "format": "json", "fields": "accession", "size": 1}
    data = await _safe_get(f"{UNIPROT_BASE}/search", params=params)
    acc = None
    if isinstance(data, dict):
        results = data.get("results") or []
        if results:
            acc = results[0].get("primaryAccession") or results[0].get("accession")
    _set_cached(cache_key, acc)
    return acc


def _extract_uniprot_name(data: dict) -> str:
    """提取蛋白推荐名称"""
    try:
        proteins = data.get("proteinDescription", {}).get("recommendedName", {})
        return proteins.get("fullName", {}).get("value", "")
    except (AttributeError, TypeError):
        return ""


def _extract_uniprot_gene(data: dict) -> str:
    """提取主基因符号"""
    try:
        genes = data.get("genes", [])
        if genes:
            return genes[0].get("geneName", {}).get("value", "")
    except (AttributeError, TypeError):
        pass
    return ""


def _extract_uniprot_function(data: dict) -> str:
    """提取蛋白功能描述（取第一条评论）"""
    try:
        comments = data.get("comments", [])
        for c in comments:
            if c.get("commentType") == "FUNCTION":
                texts = c.get("texts", [])
                if texts:
                    return texts[0].get("value", "")
    except (AttributeError, TypeError):
        pass
    return ""


def _extract_uniprot_pathways(data: dict) -> list[str]:
    """提取关联的 KEGG 通路 ID"""
    pathways = []
    try:
        db_refs = data.get("uniProtKBCrossReferences", [])
        for ref in db_refs:
            if ref.get("database") == "KEGG":
                pathways.append(ref.get("id", ""))
    except (AttributeError, TypeError):
        pass
    return pathways


def _extract_uniprot_location(data: dict) -> str:
    """提取亚细胞定位"""
    try:
        comments = data.get("comments", [])
        for c in comments:
            if c.get("commentType") == "SUBCELLULAR_LOCATION":
                locs = c.get("subcellularLocations", [])
                if locs:
                    return locs[0].get("location", {}).get("value", "")
    except (AttributeError, TypeError):
        pass
    return ""


# ---------------------------------------------------------------------------
# ClinVar (NCBI e-utilities)
# ---------------------------------------------------------------------------

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def fetch_clinvar(variant: str) -> dict | None:
    """
    通过 NCBI ClinVar e-utilities 获取变异临床意义。

    Args:
        variant: 变异描述，如 "rs1042522" 或 "NM_000546.5:c.215C>G"

    Returns:
        解析后的临床意义字典，失败返回 None
    """
    cache_key = f"clinvar:{variant}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Step 1: esearch 获取 ClinVar ID
    search_params = {
        "db": "clinvar",
        "term": variant,
        "retmode": "json",
        "retmax": 1,
    }
    search_data = await _safe_get(f"{NCBI_EUTILS}/esearch.fcgi", params=search_params)

    if not search_data or not isinstance(search_data, dict):
        return None

    id_list = search_data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        logger.info(f"ClinVar 未找到变异: {variant}")
        return None

    # Step 2: esummary 获取详情
    summary_params = {
        "db": "clinvar",
        "id": ",".join(id_list),
        "retmode": "json",
    }
    summary_data = await _safe_get(f"{NCBI_EUTILS}/esummary.fcgi", params=summary_params)

    if not summary_data or not isinstance(summary_data, dict):
        return None

    result = _parse_clinvar_summary(summary_data, id_list[0])

    if result:
        _set_cached(cache_key, result)
    return result


def _parse_clinvar_summary(data: dict, clinvar_id: str) -> dict | None:
    """解析 ClinVar esummary 返回"""
    try:
        result = data.get("result", {})
        record = result.get(clinvar_id, {})

        clinical_significance = record.get("clinical_significance", {})
        return {
            "clinvar_id": clinvar_id,
            "title": record.get("title", ""),
            "clinical_significance": clinical_significance.get("description", ""),
            "review_status": clinical_significance.get("review_status", ""),
            "variation_type": record.get("variation_type", ""),
            "gene_symbol": record.get("genes", [{}])[0].get("symbol", "") if record.get("genes") else "",
        }
    except (AttributeError, TypeError, IndexError) as exc:
        logger.warning(f"解析 ClinVar 数据失败 | error={exc}")
        return None


# ---------------------------------------------------------------------------
# KEGG
# ---------------------------------------------------------------------------

KEGG_REST = "https://rest.kegg.jp"


async def fetch_kegg_pathway(pathway_id: str) -> dict | None:
    """
    通过 KEGG REST API 获取通路信息。

    Args:
        pathway_id: KEGG 通路 ID，如 "hsa04115"

    Returns:
        解析后的通路信息字典，失败返回 None
    """
    cache_key = f"kegg:{pathway_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"{KEGG_REST}/get/{pathway_id}"
    data = await _safe_get(url)

    if data is None:
        return None

    result = _parse_kegg_pathway(data, pathway_id)

    if result:
        _set_cached(cache_key, result)
    return result


def _parse_kegg_pathway(data: dict | list, pathway_id: str) -> dict | None:
    """解析 KEGG 通路数据"""
    try:
        raw_text = data.get("raw_text", "") if isinstance(data, dict) else str(data)
        if not raw_text:
            return None

        lines = raw_text.split("\n")
        info: dict[str, str] = {}
        gene_list: list[str] = []

        for line in lines:
            if line.startswith("NAME") and not info.get("name"):
                info["name"] = line.split(" ", 1)[1].strip() if " " in line else ""
            elif line.startswith("DESCRIPTION") and not info.get("description"):
                info["description"] = line.split(" ", 1)[1].strip() if " " in line else ""
            elif line.startswith("GENE"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    gene_symbols = parts[1].strip().split(" ")
                    for gs in gene_symbols:
                        if gs and "(" not in gs:
                            gene_list.append(gs)

        return {
            "pathway_id": pathway_id,
            "name": info.get("name", ""),
            "description": info.get("description", ""),
            "genes": gene_list,
        }
    except Exception as exc:
        logger.warning(f"解析 KEGG 通路数据失败 | error={exc}")
        return None


# ---------------------------------------------------------------------------
# STRING
# ---------------------------------------------------------------------------

STRING_API = "https://version-12-0.string-db.org/api"


async def fetch_string_network(gene_symbols: list[str], species: int = 9606) -> dict | None:
    """
    通过 STRING API 获取蛋白互作网络。

    Args:
        gene_symbols: 基因符号列表，如 ["TP53", "BRCA1", "MDM2"]
        species: 物种 ID，默认 9606（人类）

    Returns:
        解析后的互作网络数据，失败返回 None
    """
    if not gene_symbols:
        return None

    cache_key = f"string:{','.join(sorted(gene_symbols))}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    params = {
        "identifiers": "\r".join(gene_symbols),
        "species": species,
        "required_score": 400,
        "limit": 50,
    }

    # 使用 network interaction 端点
    url = f"{STRING_API}/json/network"
    data = await _safe_get(url, params=params)

    if data is None or not isinstance(data, list):
        return None

    result = {
        "query_genes": gene_symbols,
        "interactions": [
            {
                "gene_a": item.get("preferredName_A", ""),
                "gene_b": item.get("preferredName_B", ""),
                "score": item.get("score", 0),
                "ncbi_id_a": item.get("ncbiTaxonId", ""),
                "ncbi_id_b": "",
            }
            for item in data
        ],
    }

    _set_cached(cache_key, result)
    return result