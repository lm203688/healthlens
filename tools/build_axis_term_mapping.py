#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S1-2 四向映射表生成器
=====================
产出 data/axis_term_mapping.json / .md：

  GB/T 20348-2026 国标术语（含英文，待官方标准原文校验）
      ↔ 八轴（A–H，代码已实现且案例使用的轴）
      ↔ 通路（pathway_to_syndrome_map.json）
      ↔ 古籍原文（classical_books.json 书目 + tcm_structured 原文片段）

诚实约束：
- GB/T 20348-2026 正文未 vendored 到本地（商业标准），国标术语为基于中医基础理论的通行对应，
  字段 gbt_confirmation_required=true，需对照官方标准原文校订英文与定义。
- 古籍原文仅引用已结构化（tcm_structured/*.json 含 source_quote）的书目，未 vendored 原文的只列书目。
- I（外泌体）/J（再生）轴在数据层被定义但案例未使用、代码未实现，单独标注为 reserved。
"""
import json
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# GB/T 20348-2026《中医基础理论术语》通行对应（需官方原文校验）
GBT_TERMS = {
    "A": {"zh": "气化", "en": "Qi Transformation", "note": "气机 / 气化失常对应代谢紊乱"},
    "B": {"zh": "气血", "en": "Qi and Blood", "note": "气血失调 / 血虚 / 气虚"},
    "C": {"zh": "络脉 / 瘀血", "en": "Collaterals / Blood Stasis", "note": "络病 / 血瘀证"},
    "D": {"zh": "阴阳 / 昼夜", "en": "Yin-Yang / Circadian", "note": "阴阳失调 / 昼夜节律"},
    "E": {"zh": "脏腑", "en": "Zang-Fu (Viscera)", "note": "脏腑辨证 / 五脏功能"},
    "F": {"zh": "正邪 / 邪正盛衰", "en": "Healthy Qi vs Pathogenic Qi", "note": "正气 / 邪气 / 虚实"},
    "G": {"zh": "神 / 情志", "en": "Spirit (Shen) / Emotion", "note": "心神 / 情志失调"},
    "H": {"zh": "先天之精 / 肾", "en": "Kidney Essence (Jing) / Congenital", "note": "肾精 / 先天禀赋"},
}

AXIS_LABELS = {  # 取自 case_evidence_db.json meta.axes_legend（仅 A–H 活跃轴）
    "A": "气化轴(AMPK/mTOR 自噬-合成代谢)",
    "B": "气血-线粒体轴(PGC-1α/SIRT1)",
    "C": "络脉-清瘀轴(senolytics/SASP)",
    "D": "阴阳-昼夜轴(CLOCK/BMAL1/TRE)",
    "E": "脏腑-神经内分泌轴(HPA/肠脑)",
    "F": "正邪-炎症轴(inflammaging)",
    "G": "神-情志轴(迷走张力/HRV/EEG)",
    "H": "先天-肾精轴(干细胞龛/表观时钟)",
}


def load(p):
    return json.load(open(os.path.join(ROOT, p), encoding="utf-8"))


def extract_books(text):
    return re.findall(r"《([^》]+)》", text or "")


def main():
    pw_map = load("data/pathway_to_syndrome_map.json")["pathways"]
    books = load("data/classical_books.json")  # 701 书目元数据
    book_titles = {b["title"] for b in books}

    # tcm_structured 已结构化的古籍（含 source_quote 原文片段）
    structured = {}
    for fn in ("神农本草经.json", "食疗本草.json"):
        try:
            d = load(f"data/tcm_structured/{fn}")
            structured[d["book"]] = d
        except Exception:
            pass

    ax2pw = defaultdict(list)
    ax2syn = defaultdict(list)
    ax2book = defaultdict(set)

    # 1) 通路 → 轴 / 证候 / 《古籍》（证候中若含《》则提取）
    for pkey, pval in pw_map.items():
        for ax in pval.get("axes", []):
            if ax in AXIS_LABELS:
                ax2pw[ax].append(pkey)
                for syn in pval.get("syndromes", []):
                    ax2syn[ax].append(syn)
                    for b in extract_books(syn):
                        ax2book[ax].add(b)

    # 2) HL- 验证夹具（真实数据）→ 轴 ↔ 古籍：symptom 含轴名，tcm_source 含《书》
    case_db = load("data/case_evidence_db.json")
    legend = case_db["meta"]["axes_legend"]
    prefix2ax = {legend[a].split("(")[0].rstrip("轴"): a for a in "ABCDEFGH" if a in legend}
    for c in case_db["cases"]:
        if not c.get("case_id"):
            continue
        sym = c.get("symptom", "")
        ax = next((a for pref, a in prefix2ax.items() if pref in sym), None)
        if not ax:
            continue
        for b in extract_books(c.get("tcm_source", "")):
            ax2book[ax].add(b)

    mapping = {"schema": "axis-term-mapping/v1", "generated_at": "2026-10-13",
               "note": "GB/T 20348-2026 术语为通行对应，gbt_confirmation_required=true，需对照官方标准校订；"
                       "古籍原文仅对 tcm_structured 中已结构化书目提供 source_quote。",
               "reserved_axes": {
                   "I": "外泌体-细胞通讯轴（数据层 pathway 映射已涉，但案例未使用、代码未实现）",
                   "J": "再生医学轴（定义未实现）"},
               "axes": {}}

    for ax in "ABCDEFGH":
        books_hit = sorted(ax2book[ax])
        # 已结构化原文片段（取前 3 条作示例）
        quotes = []
        for btitle in books_hit:
            if btitle in structured:
                ents = structured[btitle].get("entities", [])
                for e in ents[:2]:
                    q = e.get("source_quote", "")
                    if q:
                        quotes.append({"book": btitle, "entity": e.get("name"),
                                       "quote": q[:120]})
                if len(quotes) >= 6:
                    break
        mapping["axes"][ax] = {
            "axis_label": AXIS_LABELS[ax],
            "gbt_20348_2026": {**GBT_TERMS[ax], "gbt_confirmation_required": True},
            "pathways": sorted(ax2pw[ax]),
            "pathway_count": len(ax2pw[ax]),
            "representative_syndromes": sorted(set(ax2syn[ax]))[:12],
            "classical_books": books_hit,
            "classical_quotes_sample": quotes,
        }

    out_json = os.path.join(ROOT, "data", "axis_term_mapping.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    # Markdown 摘要
    lines = ["# HealthLens 四向映射表（GB/T 20348-2026 ↔ 八轴 ↔ 通路 ↔ 古籍）\n",
             "> 生成：2026-10-13 ｜ 国标术语为通行对应，需对照 GB/T 20348-2026 官方原文校订英文与定义。\n",
             "> 古籍原文仅对 tcm_structured 中已结构化书目提供片段；其余仅列书目。\n"]
    lines.append("| 轴 | 国标术语(中/英) | 关联通路数 | 代表证候 | 关联古籍 |")
    lines.append("|---|---|---|---|---|")
    for ax in "ABCDEFGH":
        m = mapping["axes"][ax]
        gbt = m["gbt_20348_2026"]
        syn = "、".join(m["representative_syndromes"][:4])
        bks = "、".join(m["classical_books"][:4]) or "—"
        lines.append(f"| {ax} {m['axis_label'].split('(')[0]} | {gbt['zh']} / {gbt['en']} | {m['pathway_count']} | {syn} | {bks} |")
    lines.append("")
    lines.append("## 各轴明细\n")
    for ax in "ABCDEFGH":
        m = mapping["axes"][ax]
        gbt = m["gbt_20348_2026"]
        lines.append(f"### 轴 {ax} · {m['axis_label']}\n")
        lines.append(f"- **GB/T 20348-2026**：{gbt['zh']}（{gbt['en']}）— {gbt['note']}  ⚠️需官方原文校验")
        lines.append(f"- **通路（{m['pathway_count']}）**：{', '.join(m['pathways'])}")
        lines.append(f"- **代表证候**：{', '.join(m['representative_syndromes'])}")
        lines.append(f"- **关联古籍**：{', '.join(m['classical_books']) or '—'}")
        if m["classical_quotes_sample"]:
            lines.append("- **古籍原文示例**：")
            for q in m["classical_quotes_sample"][:3]:
                lines.append(f"  - 《{q['book']}·{q['entity']}》：{q['quote']}…")
        lines.append("")

    out_md = os.path.join(ROOT, "data", "axis_term_mapping.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"wrote {out_json} and {out_md}")
    print("axes mapped:", list(mapping['axes'].keys()))


if __name__ == "__main__":
    main()
