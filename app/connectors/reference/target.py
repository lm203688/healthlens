"""靶点桥接 — 基因符号 → 蛋白 → 结构证据

这是把四个参考库串成一条链的地方，也是本项目「专业化」最直接的落点：

    基因符号 (如 TP53)
        ↓ UniProt          解析登录号 (P04637)
        ↓ RCSB PDB         实验测定结构（有分辨率，可作结构证据）
        ↓ AlphaFold DB     预测结构（有 pLDDT，不可作实验证据）

对 HealthLens 的意义：八轴/证据卡里出现的任何靶点，都能从「一句结论」下沉到
「已发表结构 + 结合配体 + 预测模型」，这是审稿人和 B 端客户都会问的那一层。
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.connectors.reference.alphafold import AlphaFoldDB
from app.connectors.reference.base import ReferenceError
from app.connectors.reference.rcsb import RCSBPDB
from app.connectors.reference.uniprot import UniProt


async def describe_target(
    gene_symbol: str,
    *,
    organism_id: int = 9606,
    max_structures: int = 10,
    include_structure_details: int = 3,
) -> dict[str, Any]:
    """一次拿全一个靶点的蛋白元数据 + 实验结构 + 预测结构。

    Args:
        gene_symbol: HGNC 基因符号（TP53 / ACTB / EGFR ...）
        organism_id: NCBI taxonomy，默认 9606（人）
        max_structures: 最多返回多少个 PDB ID
        include_structure_details: 前 N 个结构额外取标题/方法/分辨率
            （每个额外结构 = 1 次请求，默认 3 以控制时延）

    失败语义：UniProt 解析不到 → 抛 not_found；结构库失败 → 该字段返回
    `{"ok": false, "error": {...}}` 而不拖垮整个响应（结构是增强信息，
    不是主结果）。这种「主结果严格、增强结果可降级」的取舍是刻意的。
    """
    uniprot = UniProt()
    rcsb = RCSBPDB()
    alphafold = AlphaFoldDB()

    protein = await uniprot.resolve_gene(gene_symbol, organism_id=organism_id)
    accession = protein["accession"]

    structures_task = _safe(rcsb.search_by_uniprot(accession, limit=max_structures))
    predicted_task = _safe(alphafold.predictions(accession))
    structures, predicted = await asyncio.gather(structures_task, predicted_task)

    details: list[dict[str, Any]] = []
    if structures.get("ok") and include_structure_details > 0:
        ids = structures["data"]["ids"][:include_structure_details]
        fetched = await asyncio.gather(*[_safe(rcsb.entry(pid)) for pid in ids])
        details = [f["data"] for f in fetched if f.get("ok")]

    return {
        "gene_symbol": gene_symbol,
        "organism_id": organism_id,
        "protein": protein,
        "experimental_structures": {
            **structures,
            "details": details,
            "note": "RCSB 实验测定结构，可作结构证据；分辨率越低越好",
        },
        "predicted_structure": {
            **predicted,
            "note": "AlphaFold 计算预测，仅用于无实验结构时的形态参考",
        },
        "evidence_policy": (
            "实验结构与预测结构必须分别标注；不得把 AlphaFold 模型计入 L1/L2 证据等级"
        ),
        "source_chain": ["uniprot", "rcsb_pdb", "alphafold"],
    }


async def _safe(coro) -> dict[str, Any]:
    """把单个源的失败收敛为结构化结果，避免一个源拖垮整条链。"""
    try:
        data = await coro
    except ReferenceError as exc:
        return {"ok": False, "error": exc.to_dict()}
    except Exception as exc:  # 连接器内部未预期异常也不能静默
        return {
            "ok": False,
            "error": {"code": "upstream_error", "detail": f"{type(exc).__name__}: {exc}"},
        }
    return {"ok": True, "data": data}
