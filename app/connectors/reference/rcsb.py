"""RCSB PDB 连接器 — 实验测定三维结构档案库

上游：
  - data.rcsb.org      REST + GraphQL（条目元数据、实体、配体）
  - search.rcsb.org    Search API v2（全库检索）

为什么主路径用 GraphQL：一个条目要同时拿「标题/方法/分辨率/作者/聚合物实体/
来源物种/非聚合物配体」共 7 类信息，REST 需要 1 + N + M 次请求，GraphQL 一次
拿全。检索仍走 Search API（它只有 REST 形态）。

免费、无需 key。政策见 https://www.rcsb.org/pages/policies。
"""
from __future__ import annotations

from typing import Any

from app.connectors.reference.base import (
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    as_list,
)

#: 单次 GraphQL 拉全条目。字段名已对 data.rcsb.org 实测校验（2026-11-01）。
_ENTRY_QUERY = """
query($id: String!) {
  entry(entry_id: $id) {
    rcsb_id
    struct { title }
    exptl { method }
    rcsb_entry_info {
      experimental_method
      resolution_combined
      molecular_weight
      deposited_polymer_monomer_count
    }
    rcsb_accession_info { initial_release_date deposit_date }
    audit_author { name }
    polymer_entities {
      rcsb_id
      entity_poly { pdbx_strand_id type rcsb_sample_sequence_length }
      rcsb_polymer_entity { pdbx_description }
      rcsb_entity_source_organism { scientific_name ncbi_taxonomy_id }
    }
    nonpolymer_entities {
      rcsb_id
      nonpolymer_comp { chem_comp { id name formula } }
    }
  }
}
"""


class RCSBPDB(ReferenceSource):
    SOURCE = "rcsb_pdb"
    DISPLAY_NAME = "RCSB Protein Data Bank"
    BASE_URL = "https://data.rcsb.org"
    SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
    MIN_INTERVAL = 0.0  # RCSB 未公布硬性 req/s；默认不限速，靠缓存
    DEFAULT_TTL = 86400.0  # 已发布结构不会变，缓存一天

    # -- 内部 ---------------------------------------------------------------
    async def _graphql(self, pdb_id: str) -> dict[str, Any]:
        payload = await self._post_json(
            "https://data.rcsb.org/graphql",
            json_body={"query": _ENTRY_QUERY, "variables": {"id": pdb_id}},
            ttl=self.DEFAULT_TTL,
        )
        if payload.get("errors"):
            msg = payload["errors"][0].get("message", "GraphQL error")
            raise ReferenceError("upstream_error", self.SOURCE, msg)
        entry = (payload.get("data") or {}).get("entry")
        if not entry:
            raise ReferenceError("not_found", self.SOURCE, f"PDB entry {pdb_id} 不存在", status=404)
        return entry

    # -- 公开方法 -----------------------------------------------------------
    async def entry(self, pdb_id: str) -> dict[str, Any]:
        """单条 REST 元数据（轻量，适合列表页快速取字段）。"""
        pid = self._normalize_id(pdb_id)
        data = await self._get_json(f"/rest/v1/core/entry/{pid}")
        info = data.get("rcsb_entry_info") or {}
        return {
            "pdb_id": data.get("rcsb_id", pid),
            "title": ((data.get("struct") or {}).get("title") or "").strip(),
            "experimental_methods": [
                m.get("method") for m in as_list(data.get("exptl")) if m.get("method")
            ],
            "resolution_angstrom": _first_float(info.get("resolution_combined")),
            "molecular_weight_kda": _round(info.get("molecular_weight")),
            "polymer_monomer_count": info.get("deposited_polymer_monomer_count"),
            "released_at": (data.get("rcsb_accession_info") or {}).get("initial_release_date"),
            "deposited_at": (data.get("rcsb_accession_info") or {}).get("deposit_date"),
            "authors": [a.get("name") for a in as_list(data.get("audit_author")) if a.get("name")],
            "source": self.SOURCE,
            "source_url": f"https://www.rcsb.org/structure/{pid}",
        }

    async def describe(self, pdb_id: str) -> dict[str, Any]:
        """完整描述：元数据 + 聚合物实体 + 配体。一次 GraphQL 请求。"""
        pid = self._normalize_id(pdb_id)
        entry = await self._graphql(pid)
        info = entry.get("rcsb_entry_info") or {}
        accession = entry.get("rcsb_accession_info") or {}

        polymers = []
        for pe in as_list(entry.get("polymer_entities")):
            poly = pe.get("entity_poly") or {}
            orgs = as_list(pe.get("rcsb_entity_source_organism"))
            polymers.append(
                {
                    "entity_id": pe.get("rcsb_id"),
                    "description": (pe.get("rcsb_polymer_entity") or {}).get("pdbx_description"),
                    "chains": [c.strip() for c in (poly.get("pdbx_strand_id") or "").split(",") if c.strip()],
                    "molecule_type": poly.get("type"),
                    "length": poly.get("rcsb_sample_sequence_length"),
                    "organisms": [
                        {
                            "scientific_name": o.get("scientific_name"),
                            "taxonomy_id": o.get("ncbi_taxonomy_id"),
                        }
                        for o in orgs
                        if o.get("scientific_name")
                    ],
                }
            )

        ligands = []
        for ne in as_list(entry.get("nonpolymer_entities")):
            comp = ((ne.get("nonpolymer_comp") or {}).get("chem_comp")) or {}
            if not comp.get("id"):
                continue
            ligands.append(
                {
                    "entity_id": ne.get("rcsb_id"),
                    "comp_id": comp.get("id"),
                    "name": comp.get("name"),
                    "formula": comp.get("formula"),
                }
            )

        return {
            "pdb_id": entry.get("rcsb_id", pid),
            "title": ((entry.get("struct") or {}).get("title") or "").strip(),
            "experimental_methods": [
                m.get("method") for m in as_list(entry.get("exptl")) if m.get("method")
            ],
            "resolution_angstrom": _first_float(info.get("resolution_combined")),
            "molecular_weight_kda": _round(info.get("molecular_weight")),
            "polymer_monomer_count": info.get("deposited_polymer_monomer_count"),
            "released_at": accession.get("initial_release_date"),
            "deposited_at": accession.get("deposit_date"),
            "authors": [a.get("name") for a in as_list(entry.get("audit_author")) if a.get("name")],
            "polymer_entities": polymers,
            "ligands": ligands,
            "entity_count": {"polymer": len(polymers), "nonpolymer": len(ligands)},
            "source": self.SOURCE,
            "source_url": f"https://www.rcsb.org/structure/{pid}",
        }

    async def search(
        self,
        *,
        text: str | None = None,
        method: str | None = None,
        max_resolution: float | None = None,
        organism: str | None = None,
        released_after: str | None = None,
        limit: int = 25,
        start: int = 0,
    ) -> dict[str, Any]:
        """全库检索。

        多个条件之间是 AND。`text` 走全文检索，其余走属性过滤。
        注意：RCSB 的属性过滤值区分大小写，method 需传完整方法名
        （如 "X-RAY DIFFRACTION" / "ELECTRON MICROSCOPY" / "SOLUTION NMR"）。
        """
        nodes: list[dict[str, Any]] = []

        if text:
            nodes.append(
                {"type": "terminal", "service": "full_text", "parameters": {"value": text}}
            )
        if method:
            nodes.append(_attr("exptl.method", "exact_match", method))
        if max_resolution is not None:
            nodes.append(_attr("rcsb_entry_info.resolution_combined", "less", max_resolution))
        if organism:
            nodes.append(
                _attr(
                    "rcsb_entity_source_organism.scientific_name",
                    "contains_phrase",
                    organism,
                )
            )
        if released_after:
            nodes.append(
                _attr("rcsb_accession_info.initial_release_date", "greater", released_after)
            )

        if not nodes:
            raise ReferenceError("invalid_input", self.SOURCE, "至少需要一个检索条件")
        if limit < 1 or limit > 100:
            raise ReferenceError("invalid_input", self.SOURCE, "limit 需在 1..100")

        query: dict[str, Any]
        if len(nodes) == 1:
            query = nodes[0]
        else:
            query = {"type": "group", "logical_operator": "and", "nodes": nodes}

        body = {
            "query": query,
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": max(0, start), "rows": limit},
                "sort": [
                    {"sort_by": "rcsb_accession_info.initial_release_date", "direction": "desc"}
                ],
            },
        }
        payload = await self._post_json(self.SEARCH_URL, json_body=body, ttl=600)
        result_set = as_list(payload.get("result_set"))
        return {
            "total_count": payload.get("total_count", 0),
            "returned": len(result_set),
            "start": start,
            "ids": [r.get("identifier") for r in result_set if r.get("identifier")],
            "scores": [r.get("score") for r in result_set],
            "query_used": query,
            "source": self.SOURCE,
        }

    async def search_by_uniprot(
        self, accession: str, *, limit: int = 25, start: int = 0
    ) -> dict[str, Any]:
        """按 UniProt 登录号检索已解析结构。

        这是「某个蛋白有哪些实验结构」的标准入口——RCSB 用
        `reference_sequence_identifiers.database_accession` 索引 UniProt 号。
        """
        acc = (accession or "").strip().upper()
        if not acc:
            raise ReferenceError("invalid_input", self.SOURCE, "accession 不能为空")
        body = {
            "query": _attr(
                "rcsb_polymer_entity_container_identifiers"
                ".reference_sequence_identifiers.database_accession",
                "exact_match",
                acc,
            ),
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": max(0, start), "rows": max(1, min(limit, 100))},
                "sort": [
                    {"sort_by": "rcsb_accession_info.initial_release_date", "direction": "desc"}
                ],
            },
        }
        payload = await self._post_json(self.SEARCH_URL, json_body=body, ttl=1800)
        result_set = as_list(payload.get("result_set"))
        return {
            "uniprot_accession": acc,
            "total_count": payload.get("total_count", 0),
            "returned": len(result_set),
            "ids": [r.get("identifier") for r in result_set if r.get("identifier")],
            "source": self.SOURCE,
        }

    async def health(self) -> dict[str, Any]:
        data = await self._get_json("/rest/v1/core/entry/4HHB", ttl=60)
        return {"status": "ok", "probe": data.get("rcsb_id"), "title": (data.get("struct") or {}).get("title")}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url=self.BASE_URL,
            requires_key=False,
            operations=["entry", "describe", "search", "search_by_uniprot"],
            rate_limit="无硬性公布限额；结果按 PDB ID 缓存 24h",
            notes="GraphQL 一次取全条目；检索值区分大小写",
        )

    @staticmethod
    def _normalize_id(pdb_id: str) -> str:
        pid = (pdb_id or "").strip().upper()
        if len(pid) != 4 or not pid.isalnum():
            raise ReferenceError(
                "invalid_input", RCSBPDB.SOURCE, f"PDB ID 必须是 4 位字母数字，收到: {pdb_id!r}"
            )
        return pid


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _attr(attribute: str, operator: str, value: Any) -> dict[str, Any]:
    return {
        "type": "terminal",
        "service": "text",
        "parameters": {"attribute": attribute, "operator": operator, "value": value},
    }


def _first_float(values: Any) -> float | None:
    for v in as_list(values):
        if isinstance(v, (int, float)):
            return round(float(v), 3)
    return None


def _round(value: Any, digits: int = 2) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    return None
