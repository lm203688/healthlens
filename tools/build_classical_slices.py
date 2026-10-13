"""古籍原文切片 + 八轴启发式标注 — S1-3（2026-10-13）

从 `data/tcm_structured/`（神农本草经 / 食疗本草，共 613 条带真实 source_quote 的
实体）切出原文段落，并按八轴(A–H)给出**启发式初标**。

诚实边界（务必随产物一起读）：
- 段落文本 = 结构化数据里的真实 `source_quote`（去掉「内容：」前缀、剥离尾部校勘
  引文），来源可溯源到具体典籍与实体，绝非编造。
- 八轴标注 = 基于轴标签语义的透明关键词启发式（规则见 AXIS_KEYWORDS，可复现），
  **不是权威轴归属**。古代本草先于这套现代整合医学轴框架，关键词匹配只能给出
  「候选提示」。每条都带 `needs_expert_review: true`，须经领域专家复核后方可入
  正式知识层。与号脉阈值「未标定」同类诚实处理。
"""
from __future__ import annotations

import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "data", "classical_slices.json")
OUT_MD = os.path.join(ROOT, "data", "classical_slices.md")

# 轴语义锚点关键词（透明、可复现；由 AXIS_META 标签语义派生，非权威词典）
AXIS_KEYWORDS: dict[str, list[str]] = {
    "A": ["气化", "阳气", "温煦", "运化", "升降", "化气", "通气", "益气", "生气"],
    "B": ["心血", "营血", "血脉", "气血", "补虚", "虚弱", "羸瘦", "养", "益血", "血"],
    "C": ["经络", "孙络", "血瘀", "瘀", "通利", "通血脉", "络脉", "周痹", "肢节"],
    "D": ["阴阳", "寒热", "阴虚", "阳虚", "寐", "寤", "安眠", "睡眠", "时行", "潮热"],
    "E": ["五脏", "六腑", "脏腑", "心腹", "肝", "肺", "脾胃", "三焦", "胃", "肠"],
    "F": ["邪气", "寒邪", "风邪", "湿邪", "热毒", "疫", "蛊", "杀虫", "辟恶", "除恶", "杀", "邪"],
    "G": ["魂魄", "精神", "安神", "神志", "志", "喜", "怒", "惊", "忧", "思", "忘", "多忘"],
    "H": ["肾精", "先天", "久服", "不老", "延年", "益精", "种子", "聪", "发", "肾气"],
}
AXIS_LABELS = {
    "A": "气化-自噬(AMPK-mTOR)", "B": "气血-线粒体能量(NAD+/mtDNA)",
    "C": "络脉-内皮微循环", "D": "阴阳-昼夜节律", "E": "脏腑-神经内分泌(HPA)",
    "F": "正邪-炎症负荷", "G": "神-情志(自主神经)", "H": "先天-肾精(表观遗传)",
}

# 尾部校勘/引文起始标志（用于把正文与校勘注分离）
_CIT_START = re.compile(r"[（(]\s*(?:《|引|校|谨按|按|见图|参|汪|纲目|别录|本草)")


def _split_quote(raw: str) -> tuple[str, str]:
    """去掉『内容：』前缀，剥离尾部校勘引文 → (正文, 引文)。"""
    text = raw.strip()
    for pre in ("内容：", "内容:", "原文：", "原文:"):
        if text.startswith(pre):
            text = text[len(pre):].strip()
            break
    # 只在后半段找校勘注起点，避免误伤正文里的括号
    head, tail = text[: int(len(text) * 0.6)], text[int(len(text) * 0.6):]
    m = _CIT_START.search(tail)
    if m:
        cut = int(len(text) * 0.6) + m.start()
        main = text[:cut].rstrip("。，、 （(").strip()
        citation = text[cut:].strip().strip("（）()").strip()
        return main, citation
    return text.strip(), ""


def _annotate_axis(text: str) -> dict:
    """关键词启发式八轴标注：返回主轴/次轴/命中词/置信度。透明可复现。"""
    scores: dict[str, list[str]] = {}
    for ax, kws in AXIS_KEYWORDS.items():
        hits = [kw for kw in kws if kw in text]
        if hits:
            scores[ax] = hits
    if not scores:
        return {"axis_hint": None, "axis_hint_secondary": None,
                "matched_keywords": [], "axis_confidence": 0.0}
    ranked = sorted(scores.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    primary, phits = ranked[0]
    secondary, shits = (ranked[1] if len(ranked) > 1 else (None, []))
    # 置信度：命中词越多、且与次轴拉开差距 → 越高（上限 0.8，留专家空间）
    gap = len(phits) - len(shits)
    conf = min(0.8, 0.3 + 0.12 * len(phits) + 0.05 * max(0, gap))
    return {
        "axis_hint": primary,
        "axis_hint_secondary": secondary,
        "axis_label": AXIS_LABELS[primary],
        "matched_keywords": sorted(set(phits)),
        "axis_confidence": round(conf, 2),
    }


def build() -> list[dict]:
    slices: list[dict] = []
    for fp in sorted(glob.glob(os.path.join(ROOT, "data", "tcm_structured", "*.json"))):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        book = data.get("book") or os.path.splitext(os.path.basename(fp))[0]
        author = data.get("author", "")
        dynasty = data.get("dynasty", "")
        for ent in data.get("entities", []):
            raw = (ent.get("source_quote") or "").strip()
            if len(raw) < 12:
                continue
            main, citation = _split_quote(raw)
            if len(main) < 10:
                continue
            context = f"{main} {ent.get('efficacy','')} {ent.get('property','')}"
            ann = _annotate_axis(context)
            slices.append({
                "slice_id": f"CS-{len(slices)+1:04d}",
                "book": book,
                "author": author,
                "dynasty": dynasty,
                "entity": ent.get("name", ""),
                "entity_type": ent.get("type", ""),
                "property": ent.get("property", ""),
                "efficacy": ent.get("efficacy", ""),
                "passage": main,
                "citation": citation,
                "evidence_level": ent.get("evidence_level", ""),
                "axis_hint": ann["axis_hint"],
                "axis_hint_secondary": ann["axis_hint_secondary"],
                "axis_label": ann.get("axis_label"),
                "matched_keywords": ann["matched_keywords"],
                "axis_confidence": ann["axis_confidence"],
                "axis_method": "keyword_heuristic_v1",
                "needs_expert_review": True,
            })
    return slices


DISCLAIMER = (
    "八轴标注为基于轴标签语义的关键词启发式（keyword_heuristic_v1，规则见 "
    "tools/build_classical_slices.py 的 AXIS_KEYWORDS），仅作候选提示，非权威轴归属；"
    "本草典籍先于现代整合医学八轴框架。每条 needs_expert_review=true，须领域专家复核。"
    "段落文本取自 data/tcm_structured 的真实 source_quote，来源可溯源。"
)


def main():
    slices = build()
    covered = sum(1 for s in slices if s["axis_hint"])
    from collections import Counter
    by_axis = Counter(s["axis_hint"] for s in slices if s["axis_hint"])
    payload = {
        "meta": {
            "version": "v1.0",
            "date": "2026-10-13",
            "total_slices": len(slices),
            "axis_covered": covered,
            "axis_distribution": dict(sorted(by_axis.items())),
            "axis_method": "keyword_heuristic_v1",
            "annotation_disclaimer": DISCLAIMER,
            "needs_expert_review_all": True,
            "source": "data/tcm_structured/*.json (real source_quote)",
        },
        "slices": slices,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = [
        "# 古籍原文切片 + 八轴启发式标注（S1-3）",
        "",
        f"- 切片总数：**{len(slices)}**（目标 ≥100）",
        f"- 有轴提示：{covered}；轴分布：{dict(sorted(by_axis.items()))}",
        f"- 标注方法：`keyword_heuristic_v1`（关键词启发式）",
        "",
        f"> ⚠️ **诚实边界**：{DISCLAIMER}",
        "",
        "| slice_id | 典籍 | 实体 | 性味 | 轴提示(次) | 置信 | 命中词 |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in slices:
        sec = s["axis_hint_secondary"] or "-"
        kws = "/".join(s["matched_keywords"][:4])
        lines.append(
            f"| {s['slice_id']} | {s['book']} | {s['entity']} | {s['property']} "
            f"| {s['axis_hint']}({sec}) | {s['axis_confidence']} | {kws} |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[ok] {len(slices)} slices -> {OUT_JSON}")
    print(f"[ok] axis_distribution={dict(sorted(by_axis.items()))}")
    print(f"[ok] covered={covered}/{len(slices)}")


if __name__ == "__main__":
    main()
