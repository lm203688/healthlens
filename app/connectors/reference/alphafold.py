"""AlphaFold DB 连接器 — 预测蛋白结构

上游：https://alphafold.ebi.ac.uk/api（EBI，免费、无需 key）

定位：**预测结构，不是实验结构**。与 RCSB 严格区分：
  - RCSB：实验测定（X-ray / cryo-EM / NMR），有分辨率，可直接引用为结构证据
  - AlphaFold：计算预测，有 pLDDT 置信度，**不能**当作实验证据

本项目所有输出必须写明来源类型，不得混用（与 claims 引擎的 fail-closed 原则一致）。
"""
from __future__ import annotations

from typing import Any

from app.connectors.reference.base import (
    ReferenceError,
    ReferenceSource,
    SourceCapability,
    as_list,
)

#: pLDDT 置信度分层（AlphaFold 官方口径）
PLDDT_BANDS = [
    (90.0, "very_high", "残基级高置信，可用于结合位点分析"),
    (70.0, "confident", "主链可信，侧链需谨慎"),
    (50.0, "low", "仅粗粒度折叠判断"),
    (0.0, "very_low", "不可用于结构推断"),
]


class AlphaFoldDB(ReferenceSource):
    SOURCE = "alphafold"
    DISPLAY_NAME = "AlphaFold DB"
    BASE_URL = "https://alphafold.ebi.ac.uk/api"
    MIN_INTERVAL = 0.12
    DEFAULT_TTL = 604800.0

    async def predictions(self, accession: str) -> dict[str, Any]:
        acc = (accession or "").strip().upper()
        if not acc:
            raise ReferenceError("invalid_input", self.SOURCE, "accession 不能为空")
        raw = await self._get_json(f"/prediction/{acc}")
        entries = as_list(raw)
        if not entries:
            raise ReferenceError("not_found", self.SOURCE, f"AlphaFold 无 {acc} 的预测", status=404)
        models = [_normalize(e) for e in entries if isinstance(e, dict)]
        models.sort(key=lambda m: (m.get("plddt") or 0), reverse=True)
        return {
            "accession": acc,
            "model_count": len(models),
            "models": models,
            "best_model": models[0] if models else None,
            "evidence_type": "predicted",
            "disclaimer": "AlphaFold 为计算预测结构，非实验测定；不得作为结构证据引用",
            "source": self.SOURCE,
        }

    async def best_model(self, accession: str) -> dict[str, Any]:
        data = await self.predictions(accession)
        best = data.get("best_model")
        if not best:
            raise ReferenceError("not_found", self.SOURCE, f"{accession} 无可用模型", status=404)
        return best

    async def health(self) -> dict[str, Any]:
        data = await self._get_json("/prediction/P04637", ttl=60)
        first = as_list(data)[0] if data else {}
        return {"status": "ok", "probe": first.get("entryId")}

    def capability(self) -> SourceCapability:
        return SourceCapability(
            source=self.SOURCE,
            display_name=self.DISPLAY_NAME,
            base_url=self.BASE_URL,
            requires_key=False,
            operations=["predictions", "best_model"],
            rate_limit="无硬性限额",
            notes="预测结构，与 RCSB 实验结构严格区分",
        )


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    plddt = entry.get("globalMetricValue")
    band, band_note = _band(plddt)
    return {
        "entry_id": entry.get("entryId"),
        "uniprot_accession": entry.get("uniprotAccession"),
        "entity_type": entry.get("entityType"),
        "plddt": round(float(plddt), 2) if isinstance(plddt, (int, float)) else None,
        "plddt_band": band,
        "plddt_note": band_note,
        "coverage": {
            "start": entry.get("uniprotStart"),
            "end": entry.get("uniprotEnd"),
        },
        "created": entry.get("modelCreatedDate"),
        "version": entry.get("latestVersion"),
        "files": {
            "pdb": entry.get("pdbUrl"),
            "cif": entry.get("cifUrl"),
            "pae_image": entry.get("paeImageUrl"),
        },
        "source": AlphaFoldDB.SOURCE,
    }


def _band(plddt: Any) -> tuple[str, str]:
    try:
        value = float(plddt)
    except (TypeError, ValueError):
        return "unknown", "无 pLDDT"
    for threshold, name, note in PLDDT_BANDS:
        if value >= threshold:
            return name, note
    return "very_low", "不可用于结构推断"
