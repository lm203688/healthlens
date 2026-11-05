"""外部参考数据库接入层

四个数据源分两类：

**公开只读库（免费、无需 key）**
    - rcsb_pdb    RCSB PDB      实验测定三维结构（X-ray / cryo-EM / NMR）
    - pubchem     PubChem       1 亿+ 化合物、计算属性、相似性搜索
    - ncbi_blast  NCBI BLAST    核酸/蛋白同源性比对
    - uniprot     UniProt       蛋白元数据、基因符号 → 登录号
    - alphafold   AlphaFold DB  预测结构（与实验结构严格区分）

**商业套件适配（需自备许可）**
    - schrodinger Schrödinger   PrepWizard / Glide / MM-GBSA / FEP+ / Desmond 等

用法：
    from app.connectors.reference import get_source

    pdb = get_source("rcsb_pdb")
    info = await pdb.describe("4HHB")

单例语义：每个数据源只实例化一次，使 TTL 缓存与限流器跨请求复用。
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.config import settings
from app.connectors.reference.alphafold import AlphaFoldDB
from app.connectors.reference.base import (
    ERROR_CODES,
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    TTLCache,
    safe_health,
)
from app.connectors.reference.blast import NCBIBlast
from app.connectors.reference.pubchem import PubChem
from app.connectors.reference.rcsb import RCSBPDB
from app.connectors.reference.schrodinger import SchrodingerCADD
from app.connectors.reference.target import describe_target
from app.connectors.reference.uniprot import UniProt

__all__ = [
    "ERROR_CODES",
    "ReferenceError",
    "ReferenceSource",
    "SourceCapability",
    "TTLCache",
    "describe_target",
    "get_source",
    "list_sources",
    "probe_all",
]

_SINGLETONS: dict[str, ReferenceSource] = {}


def _build(source: str) -> ReferenceSource:
    if source == "rcsb_pdb":
        return RCSBPDB()
    if source == "pubchem":
        return PubChem()
    if source == "ncbi_blast":
        return NCBIBlast(
            api_key=getattr(settings, "NCBI_API_KEY", "") or "",
            email=getattr(settings, "NCBI_EMAIL", "") or "",
            tool=getattr(settings, "NCBI_TOOL", "healthlens") or "healthlens",
        )
    if source == "uniprot":
        return UniProt()
    if source == "alphafold":
        return AlphaFoldDB()
    if source == "schrodinger":
        return SchrodingerCADD()
    raise ReferenceError("invalid_input", "registry", f"未知数据源: {source!r}")


def get_source(source: str) -> ReferenceSource:
    """取数据源单例。未知名称抛 invalid_input（不返回 None）。"""
    if source not in _SINGLETONS:
        _SINGLETONS[source] = _build(source)
    return _SINGLETONS[source]


def list_sources() -> list[SourceCapability]:
    return [
        get_source(name).capability()
        for name in ("rcsb_pdb", "pubchem", "ncbi_blast", "uniprot", "alphafold", "schrodinger")
    ]


async def probe_all(*, timeout_s: float = 20.0) -> dict[str, Any]:
    """并发探活全部数据源。单个源失败不影响其他源。

    用于 /api/v1/bio/sources 的健康面板，也用于部署后自检。
    """
    names = ["rcsb_pdb", "pubchem", "ncbi_blast", "uniprot", "alphafold", "schrodinger"]
    results = await asyncio.gather(
        *[asyncio.wait_for(safe_health(get_source(n)), timeout=timeout_s) for n in names],
        return_exceptions=True,
    )
    health: dict[str, Any] = {}
    for name, item in zip(names, results):
        if isinstance(item, BaseException):
            health[name] = {
                "source": name,
                "ok": False,
                "error": {"code": "timeout", "detail": str(item)},
            }
        else:
            health[name] = item
    ok_count = sum(1 for v in health.values() if v.get("ok"))
    return {
        "ok_count": ok_count,
        "total": len(names),
        "sources": health,
        "capabilities": [cap.__dict__ for cap in list_sources()],
    }
