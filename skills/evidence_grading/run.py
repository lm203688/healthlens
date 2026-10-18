"""
evidence_grading/run.py — HealthLens 证据分级 Skill

对每条建议进行 L1/L2/L3 证据分级，输出分级结果 + 置信度。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_DB = ROOT / "data" / "case_evidence_db.json"

# 证据关键词映射
_L1_KEYWORDS = re.compile(r"(系统综述|meta|指南|guideline|consensus|consensusstatement)", re.IGNORECASE)
_L2_KEYWORDS = re.compile(r"(随机对照|rct|队列研究|cohort|临床|clinical|trial|prospective)", re.IGNORECASE)

# 古籍来源模式
_TCM_SOURCES = re.compile(r"[《〈].*?[》〉]")


def _load_evidence_db() -> dict:
    if not EVIDENCE_DB.exists():
        return {}
    data = json.loads(EVIDENCE_DB.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {str(i): item for i, item in enumerate(data)}
    return {}


def _grade_single(rec: dict, db: dict) -> dict:
    name = rec.get("name", "")
    tcm_source = rec.get("tcm_source", "") or ""
    gene_rel = rec.get("gene_relevance", "") or ""
    text = f"{name} {tcm_source} {gene_rel}"

    level = "L3"
    citations = []
    confidence = 0.3

    # L1 检查
    if _L1_KEYWORDS.search(text):
        level = "L1"
        confidence = 0.9
        citations = re.findall(_L1_KEYWORDS, text)

    # L2 检查
    if _L2_KEYWORDS.search(text):
        if level == "L3":
            level = "L2"
            confidence = 0.7
        citations.extend(re.findall(_L2_KEYWORDS, text))

    # 古籍来源 → L3
    tcm_refs = _TCM_SOURCES.findall(text)
    if tcm_refs and level == "L3":
        level = "L3"
        confidence = max(confidence, 0.5)
        citations.extend(tcm_refs)

    # 无引用
    if not citations:
        citations = ["（无引用来源）"]

    # 证据库交叉验证
    if name in db:
        entry = db[name]
        if isinstance(entry, dict):
            ev_level = entry.get("evidence_level", "")
            if ev_level in ("L1", "L2"):
                level = ev_level
                confidence = 0.85 if ev_level == "L1" else 0.65

    return {
        **rec,
        "evidence_level": level,
        "confidence": confidence,
        "citations": list(set(citations)),
        "graded": True,
    }


def run(recommendations: list[dict] = None, evidence_db_path: str = None) -> dict:
    db = _load_evidence_db()
    recs = recommendations or []

    graded = [_grade_single(r, db) for r in recs]
    summary = {"L1": 0, "L2": 0, "L3": 0, "ungraded": 0}
    for g in graded:
        summary[g.get("evidence_level", "ungraded")] = summary.get(g.get("evidence_level", "ungraded"), 0) + 1

    return {
        "graded": graded,
        "summary": summary,
        "ungraded": [g.get("name", "") for g in graded if not g.get("citations") or g["citations"] == ["（无引用来源）"]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recs", default='[{"name":"四君子汤","prescription":"补气健脾","tcm_source":"《太平惠民和剂局方》"}]')
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    recs = json.loads(args.recs)
    result = run(recommendations=recs)
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)
