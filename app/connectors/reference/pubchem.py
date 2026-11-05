"""PubChem 连接器 — NIH 化合物数据库（PUG-REST）

上游：https://pubchem.ncbi.nlm.nih.gov/rest/pug
覆盖 1 亿+ 化合物，免费、无需 key。官方建议 <= 5 req/s。

两个容易踩的坑（已实测，2026-11-01）：
  1. 相似性搜索**不能**写成 `.../similarity/smiles/{s}/cids/JSON`——上游会返回
     `PUGREST.BadRequest: Search input may not be combined with any operation`。
     正确做法是 `.../similarity/smiles/{s}/JSON`，它返回 202 + ListKey，
     再轮询 `.../compound/listkey/{key}/cids/JSON`。
  2. SMILES 必须整体 URL 编码（括号、等号都要编码），否则路径被截断。
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

from app.connectors.reference.base import (
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    as_list,
)

#: 一次取回的属性集合。全部是 PubChem 计算属性，不是实验测定值——
#: 引用时必须写明 "computed"，不能当作实测理化数据。
_PROPERTIES = (
    "MolecularFormula",
    "MolecularWeight",
    "ExactMass",
    "XLogP",
    "TPSA",
    "HBondDonorCount",
    "HBondAcceptorCount",
    "RotatableBondCount",
    "HeavyAtomCount",
    "Charge",
    "CanonicalSMILES",
    "ConnectivitySMILES",
    "InChIKey",
    "IUPACName",
)


class PubChem(ReferenceSource):
    SOURCE = "pubchem"
    DISPLAY_NAME = "PubChem (NIH)"
    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    MIN_INTERVAL = 0.21  # <= 5 req/s
    DEFAULT_TTL = 604800.0  # 化合物记录 7 天内基本不变

    # -- 解析 ---------------------------------------------------------------
    async def _cids(self, namespace: str, identifier: str) -> list[int]:
        """按命名空间解析 CID。namespace: name / smiles / inchikey / cid"""
        if namespace == "smiles":
            identifier = urllib.parse.quote(identifier, safe="")
        elif namespace == "name":
            identifier = urllib.parse.quote(identifier, safe="")
        payload = await self._get_json(f"/compound/{namespace}/{identifier}/cids/JSON")
        cids = ((payload.get("IdentifierList") or {}).get("CID")) or []
        return [int(c) for c in cids]

    async def resolve(self, query: str, *, namespace: str = "name") -> dict[str, Any]:
        """名称 / SMILES / InChIKey → CID 列表。

        `namespace` 由调用方指定；`auto` 时按 InChIKey → SMILES → 名称依次尝试，
        这是唯一能同时接受三种输入又不误判的稳妥顺序。
        """
        q = (query or "").strip()
        if not q:
            raise ReferenceError("invalid_input", self.SOURCE, "query 不能为空")

        tried: list[str] = []
        if namespace == "auto":
            candidates = []
            # InChIKey 形如 XXXXXXXXXXXXXX-XXXXXXXXXX-N（27 字符、两个连字符）
            if len(q) == 27 and q.count("-") == 2:
                candidates.append("inchikey")
            if any(ch in q for ch in "()=#[]@+\\/"):
                candidates.append("smiles")
            candidates.append("name")
        else:
            candidates = [namespace]

        for ns in candidates:
            if ns not in {"name", "smiles", "inchikey", "cid"}:
                raise ReferenceError("invalid_input", self.SOURCE, f"不支持的命名空间: {ns}")
            tried.append(ns)
            try:
                cids = await self._cids(ns, q)
            except ReferenceError as exc:
                if exc.code == "not_found":
                    continue
                raise
            if cids:
                return {
                    "query": q,
                    "namespace": ns,
                    "cids": cids,
                    "primary_cid": cids[0],
                    "ambiguous": len(cids) > 1,
                    "tried": tried,
                    "source": self.SOURCE,
                }

        raise ReferenceError(
            "not_found", self.SOURCE, f"PubChem 未收录: {q!r}（已尝试 {', '.join(tried)}）", status=404
        )

    # -- 属性 ---------------------------------------------------------------
    async def properties(self, cid: int) -> dict[str, Any]:
        props = ",".join(_PROPERTIES)
        payload = await self._get_json(f"/compound/cid/{int(cid)}/property/{props}/JSON")
        table = as_list((payload.get("PropertyTable") or {}).get("Properties"))
        if not table:
            raise ReferenceError("not_found", self.SOURCE, f"CID {cid} 无属性记录", status=404)
        raw = table[0]

        def num(key: str) -> float | None:
            v = raw.get(key)
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return {
            "cid": int(raw.get("CID", cid)),
            "molecular_formula": raw.get("MolecularFormula"),
            "molecular_weight": num("MolecularWeight"),
            "exact_mass": num("ExactMass"),
            "xlogp": num("XLogP"),
            "tpsa": num("TPSA"),
            "h_bond_donors": raw.get("HBondDonorCount"),
            "h_bond_acceptors": raw.get("HBondAcceptorCount"),
            "rotatable_bonds": raw.get("RotatableBondCount"),
            "heavy_atoms": raw.get("HeavyAtomCount"),
            "charge": raw.get("Charge"),
            "canonical_smiles": raw.get("CanonicalSMILES") or raw.get("ConnectivitySMILES"),
            "inchi_key": raw.get("InChIKey"),
            "iupac_name": raw.get("IUPACName"),
            "property_note": "均为 PubChem 计算属性（computed），非实验测定值",
            "source": self.SOURCE,
            "source_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{int(cid)}",
        }

    async def synonyms(self, cid: int, *, limit: int = 50) -> dict[str, Any]:
        payload = await self._get_json(f"/compound/cid/{int(cid)}/synonyms/JSON")
        info = as_list((payload.get("InformationList") or {}).get("Information"))
        syns = as_list((info[0] if info else {}).get("Synonym"))
        # CAS 号：形如 50-78-2（2-7 位-2 位-1 位校验位）
        cas = [s for s in syns if _looks_like_cas(s)]
        return {
            "cid": int(cid),
            "synonyms": syns[:limit],
            "total_synonyms": len(syns),
            "cas_numbers": cas,
            "source": self.SOURCE,
        }

    # -- 相似性 -------------------------------------------------------------
    async def similar(
        self,
        smiles: str,
        *,
        threshold: int = 95,
        limit: int = 50,
        timeout_s: float = 40.0,
    ) -> dict[str, Any]:
        """2D 指纹相似性搜索（Tanimoto）。

        走官方 similarity 异步接口：提交得 202 + ListKey，轮询取结果。
        若上游直接 200（缓存命中）则直接解析。
        """
        if not 1 <= threshold <= 100:
            raise ReferenceError("invalid_input", self.SOURCE, "threshold 需在 1..100")
        enc = urllib.parse.quote(smiles.strip(), safe="")

        resp = await self._request(
            "GET", f"{self.BASE_URL}/compound/similarity/smiles/{enc}/JSON",
            params={"Threshold": threshold},
        )
        payload = _safe_json(resp)

        if resp.status_code == 202 or "Waiting" in payload:
            list_key = ((payload.get("Waiting") or {}).get("ListKey"))
            if not list_key:
                raise ReferenceError("parse_error", self.SOURCE, "202 响应缺少 ListKey")
            cids = await self._poll_listkey(list_key, timeout_s)
        else:
            cids = ((payload.get("IdentifierList") or {}).get("CID")) or []

        cids = [int(c) for c in cids]
        return {
            "query_smiles": smiles,
            "threshold": threshold,
            "total_matches": len(cids),
            "cids": cids[:limit],
            "truncated": len(cids) > limit,
            "method": "PubChem 2D similarity (Tanimoto, similarity async ListKey)",
            "source": self.SOURCE,
        }

    async def _poll_listkey(self, list_key: str, timeout_s: float) -> list[int]:
        deadline = asyncio.get_event_loop().time() + timeout_s
        delay = 1.0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(delay)
            resp = await self._request(
                "GET", f"{self.BASE_URL}/compound/listkey/{list_key}/cids/JSON"
            )
            payload = _safe_json(resp)
            if resp.status_code == 200 and "IdentifierList" in payload:
                return [int(c) for c in (payload["IdentifierList"].get("CID") or [])]
            delay = min(delay * 1.6, 6.0)
        raise ReferenceError(
            "timeout", self.SOURCE, f"相似性搜索 {timeout_s}s 内未完成（ListKey={list_key}）"
        )

    # -- 组合 ---------------------------------------------------------------
    async def describe(self, query: str) -> dict[str, Any]:
        """一次拿全：解析 → 属性 → 同义词。适合前端"查一个化合物"的场景。"""
        resolved = await self.resolve(query, namespace="auto")
        cid = resolved["primary_cid"]
        props = await self.properties(cid)
        syns = await self.synonyms(cid)
        return {
            "query": query,
            "resolved_via": resolved["namespace"],
            "ambiguous": resolved["ambiguous"],
            "all_cids": resolved["cids"],
            "compound": props,
            "synonyms": syns["synonyms"],
            "cas_numbers": syns["cas_numbers"],
            "source": self.SOURCE,
        }

    async def health(self) -> dict[str, Any]:
        cids = await self._cids("name", "aspirin")
        return {"status": "ok", "probe": "aspirin", "cids": cids[:3]}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url=self.BASE_URL,
            requires_key=False,
            operations=["resolve", "properties", "synonyms", "similar", "describe"],
            rate_limit="官方建议 <=5 req/s（本实现限 0.21s/次）",
            notes="相似性搜索为异步 ListKey 流程；属性均为计算值",
        )


def _safe_json(resp) -> dict[str, Any]:
    try:
        return resp.json()
    except ValueError:
        return {}


def _looks_like_cas(value: str) -> bool:
    parts = value.split("-")
    if len(parts) != 3:
        return False
    a, b, c = parts
    if not (a.isdigit() and b.isdigit() and c.isdigit()):
        return False
    if not (2 <= len(a) <= 7 and len(b) == 2 and len(c) == 1):
        return False
    # 校验位
    digits = (a + b)[::-1]
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return total % 10 == int(c)