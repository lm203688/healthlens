"""ingest_tcm_mkg.py — TCM-MKG（中药多维知识图谱）→ HealthLens 实体库适配器

借鉴来源（开源借用研发，P1 知识层扩充）:
- 仓库: https://github.com/ZENGJingqi/GraphAI-for-TCM （MIT License）
- 数据: Zenodo DOI 10.5281/zenodo.13763953（TCM-MKG v3，30+ 权威源整合，
  对齐 ICD-11/UMLS/MeSH/DOID）
- 论文: Zeng & Jia (2025), Journal of Pharmaceutical Analysis 101342

原始 TSV 需先手动下载到 .workbuddy/cache/tcm_mkg/（raw.githubusercontent 在
本机网络下不稳定，建议带 --retry；大文件 .pt/.pkl 模型产物不下载）:
  Data/Chinese_herbal_pieces.tsv      饮片主表（CHP_ID/名称/同义词/拼音/英文/来源）
  Data/CHP_Medicinal_properties.tsv   饮片-药性关联表
  Data/Data_dictionary.md             字段字典

产出: data/tcm_mkg/chp_entities.json —— 蒸馏后的实体列表，schema 与
data/tcm_structured/*.json 的 entities[] 兼容（type/name/…/evidence_level），
并保留完整溯源元数据。幂等（确定性输出，不含运行时时间戳；入库日期由 git
提交记录承载）：重复运行字节级一致。

运行: python tools/ingest_tcm_mkg.py
"""
from __future__ import annotations

import csv
import json
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".workbuddy" / "cache" / "tcm_mkg"
OUT_DIR = ROOT / "data" / "tcm_mkg"
OUT_FILE = OUT_DIR / "chp_entities.json"

REQUIRED_FILES = {
    "Chinese_herbal_pieces.tsv": ["CHP_ID", "Chinese_herbal_pieces"],
    "CHP_Medicinal_properties.tsv": ["CHP_ID"],
}


def _read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def precheck() -> list[str]:
    problems = []
    for fname, need_cols in REQUIRED_FILES.items():
        p = CACHE / fname
        if not p.exists():
            problems.append(f"缺少 {p}（先下载，见模块 docstring）")
            continue
        cols = set(_read_tsv(p)[0].keys()) if _read_tsv(p) else set()
        missing = [c for c in need_cols if c not in cols]
        if missing:
            problems.append(f"{fname} 缺列: {missing}")
    return problems


def ingest() -> dict:
    pieces = _read_tsv(CACHE / "Chinese_herbal_pieces.tsv")
    props_path = CACHE / "CHP_Medicinal_properties.tsv"
    props: dict[str, list[dict]] = {}
    if props_path.exists():
        for row in _read_tsv(props_path):
            props.setdefault(row["CHP_ID"], []).append(row)

    entities = []
    joined = 0
    for row in pieces:
        cid = row["CHP_ID"]
        ent = {
            "type": "herb_piece",
            "id": cid,
            "name": (row.get("Chinese_herbal_pieces") or "").strip(),
            "synonyms": [s.strip() for s in (row.get("Chinese_synonyms") or "").split(";") if s.strip()],
            "pinyin": (row.get("Pinyin_term") or "").strip(),
            "english": (row.get("English_term") or "").strip(),
            "sources": [s.strip() for s in (row.get("Sources") or "").split(";") if s.strip()],
            "medicinal_properties": props.get(cid, []),
            "evidence_level": "high" if props.get(cid) else "medium",
            "provenance": "TCM-MKG v3",
        }
        if props.get(cid):
            joined += 1
        if ent["name"]:
            entities.append(ent)

    payload = {
        "source": "TCM-MKG (Traditional Chinese Medicine Multi-dimensional Knowledge Graph)",
        "origin_repo": "https://github.com/ZENGJingqi/GraphAI-for-TCM",
        "zenodo_doi": "10.5281/zenodo.13763953",
        "license": "MIT (repo code/data, Copyright (c) 2024 Zeng Jingqi)",
        "alignment": ["ICD-11", "UMLS", "MeSH", "DOID"],
        "stats": {
            "pieces_total": len(entities),
            "with_medicinal_properties": joined,
        },
        "entities": entities,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return payload


def main() -> int:
    problems = precheck()
    if problems:
        print("[precheck] 未就绪:")
        for p in problems:
            print("  -", p)
        return 1
    payload = ingest()
    s = payload["stats"]
    print(f"[ok] 写入 {OUT_FILE}")
    print(f"     饮片实体 {s['pieces_total']} 条，其中带药性 {s['with_medicinal_properties']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
