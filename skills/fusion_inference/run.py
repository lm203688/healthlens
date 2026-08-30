"""
fusion_inference/run.py — HealthLens 融合推理 Skill

封装核心融合引擎：古籍候选 ∩ 基因弱项 → 八轴评分 + 个性化建议。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# 通过 importlib 加载融合引擎（避免触发 FastAPI app 初始化）
_loader_spec = importlib.util.spec_from_file_location(
    "fusion_engine", ROOT / "app" / "lib" / "fusion_engine.py"
)
_fe_mod = importlib.util.module_from_spec(_loader_spec)
sys.modules["fusion_engine"] = _fe_mod
_loader_spec.loader.exec_module(_fe_mod)

recommend = _fe_mod.recommend
UserProfile = _fe_mod.UserProfile


def _parse_gene(text: str) -> dict[str, float]:
    scores = {}
    for part in text.split(","):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            scores[k.strip()] = float(v.strip())
    return scores


def run(
    gene_scores: dict[str, float] = None,
    text_profile: str = "",
    tcm_profile: dict = None,
    contraindications: set[str] = None,
) -> dict:
    profile = UserProfile(
        pathway_scores=gene_scores or {},
        contraindications=contraindications or set(),
    )

    # 文本弱项提取（简易规划器）
    if text_profile:
        keyword_scores = {}
        axis_keywords = {
            "A": ["疲劳", "乏力", "自噬"],
            "B": ["气短", "喘", "气血"],
            "C": ["血瘀", "瘀堵", "痛"],
            "D": ["失眠", "昼夜"],
            "F": ["炎症", "免疫"],
            "G": ["焦虑", "情志"],
            "H": ["肾", "衰老", "干细胞"],
        }
        for ax, kws in axis_keywords.items():
            for kw in kws:
                if kw.lower() in text_profile.lower():
                    keyword_scores[f"axis_{ax}_pathway"] = 0.35
                    break
        profile.pathway_scores.update(keyword_scores)

    result = recommend(profile)

    return {
        "weak_pathways": result.get("weak_pathways", []),
        "weak_axes": result.get("weak_axes", []),
        "recommendations": result.get("recommendations", []),
        "fusion_score": round(len(result.get("recommendations", [])) * 0.1, 2),
        "disclaimer": result.get("banner", ""),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="")
    parser.add_argument("--gene", default="")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    gene = _parse_gene(args.gene) if args.gene else {}
    result = run(gene_scores=gene, text_profile=args.text)
    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)
