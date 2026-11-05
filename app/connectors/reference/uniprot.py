"""UniProt 连接器 — 蛋白元数据与基因映射

上游：https://rest.uniprot.org（免费、无需 key）

用途：把「基因符号」解析成「UniProt 登录号」，这是连接 RCSB（结构）与
AlphaFold（预测结构）的枢纽——两个库都按登录号索引，不认基因名。
"""
from __future__ import annotations

from typing import Any

from app.connectors.reference.base import (
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    as_list,
)


class UniProt(ReferenceSource):
    SOURCE = "uniprot"
    DISPLAY_NAME = "UniProt"
    BASE_URL = "https://rest.uniprot.org"
    MIN_INTERVAL = 0.12
    DEFAULT_TTL = 604800.0

    async def entry(self, accession: str) -> dict[str, Any]:
        acc = (accession or "").strip().upper()
        if not acc:
            raise ReferenceError("invalid_input", self.SOURCE, "accession 不能为空")
        raw = await self._get_json(f"/uniprotkb/{acc}.json")
        return _normalize(raw)

    async def search(
        self,
        query: str,
        *,
        size: int = 5,
        reviewed_only: bool = True,
    ) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            raise ReferenceError("invalid_input", self.SOURCE, "query 不能为空")
        if reviewed_only and "reviewed" not in q:
            q = f"({q}) AND reviewed:true"
        payload = await self._get_json(
            "/uniprotkb/search",
            params={"query": q, "format": "json", "size": max(1, min(size, 25))},
        )
        results = [_normalize(r) for r in as_list(payload.get("results"))]
        return {
            "query": q,
            "count": len(results),
            "results": results,
            "source": self.SOURCE,
        }

    async def resolve_gene(
        self, gene_symbol: str, *, organism_id: int = 9606
    ) -> dict[str, Any]:
        """基因符号 → 最佳 UniProt 登录号（默认人类、仅 reviewed 条目）。"""
        symbol = (gene_symbol or "").strip()
        if not symbol:
            raise ReferenceError("invalid_input", self.SOURCE, "gene_symbol 不能为空")
        q = f"gene_exact:{symbol} AND organism_id:{organism_id} AND reviewed:true"
        found = await self.search(q, size=5, reviewed_only=False)
        if not found["results"]:
            raise ReferenceError(
                "not_found",
                self.SOURCE,
                f"UniProt 未找到 reviewed 条目：{symbol}（organism_id={organism_id}）",
                status=404,
            )
        best = found["results"][0]
        return {
            "gene_symbol": symbol,
            "organism_id": organism_id,
            "accession": best["accession"],
            "protein_name": best["protein_name"],
            "length": best["length"],
            "candidates": [r["accession"] for r in found["results"]],
            "source": self.SOURCE,
        }

    async def health(self) -> dict[str, Any]:
        data = await self._get_json("/uniprotkb/P04637.json", ttl=60)
        return {"status": "ok", "probe": data.get("primaryAccession")}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url=self.BASE_URL,
            requires_key=False,
            operations=["entry", "search", "resolve_gene"],
            rate_limit="无硬性限额，本实现限 0.12s/次",
            notes="基因→登录号解析默认限定 reviewed 人类条目",
        )


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    desc = raw.get("proteinDescription") or {}
    recommended = ((desc.get("recommendedName") or {}).get("fullName") or {}).get("value")
    submitted = [
        ((s.get("fullName") or {}).get("value"))
        for s in as_list(desc.get("submissionNames"))
    ]
    genes = [
        (g.get("geneName") or {}).get("value")
        for g in as_list(raw.get("genes"))
        if (g.get("geneName") or {}).get("value")
    ]
    organism = (raw.get("organism") or {})
    seq = raw.get("sequence") or {}
    return {
        "accession": raw.get("primaryAccession"),
        "entry_name": raw.get("uniProtkbId"),
        "protein_name": recommended or (submitted[0] if submitted else None),
        "genes": genes,
        "organism": organism.get("scientificName"),
        "taxonomy_id": organism.get("taxonId"),
        "length": seq.get("length"),
        "mass_da": seq.get("molWeight"),
        "reviewed": raw.get("entryType", "").lower().startswith("reviewed"),
        "sequence_available": bool(seq.get("value")),
        "source": UniProt.SOURCE,
        "source_url": f"https://www.uniprot.org/uniprotkb/{raw.get('primaryAccession')}/entry",
    }