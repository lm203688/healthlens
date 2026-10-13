#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/case_evidence_db.json 生成可读 Markdown 案例证据库。"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
db = json.loads((ROOT / "data" / "case_evidence_db.json").read_text(encoding="utf-8"))
cases = db["cases"]
meta = db["meta"]

lines = []
lines.append("# HealthLens 真实案例证据数据库（可读版）\n")
lines.append(f"> 版本 {meta['version']} ｜ {meta['date']} ｜ 共 {meta['total_cases']} 条案例  \n")
lines.append(f"> 用途：{meta['purpose']}\n")

lines.append("## 证据等级定义\n")
lines.append("| 等级 | 定义 |")
lines.append("|---|---|")
for k, v in meta["evidence_levels"].items():
    lines.append(f"| {k} | {v} |")
lines.append("")

lines.append("## 稳态轴图例\n")
lines.append("| 轴 | 含义 |")
lines.append("|---|---|")
for k, v in meta["axes_legend"].items():
    lines.append(f"| {k} | {v} |")
lines.append("")

# 统计
from collections import Counter
lvl = Counter(c["evidence_level"] for c in cases)
lines.append(f"## 总览：L1={lvl.get('L1',0)} ｜ L2={lvl.get('L2',0)} ｜ L3={lvl.get('L3',0)}\n")

for c in cases:
    # HL- 前缀的自动生成验证夹具（无完整证据 schema）不进入可读案例库
    if not c.get("id"):
        continue
    lines.append(f"---\n")
    lines.append(f"### {c['id']} · {c['intervention']}\n")
    lines.append(f"- **古籍对应**：{c['tcm_concept']}")
    lines.append(f"- **映射轴**：{'、'.join(c['axes'])} ｜ **现代机制**：{c['mechanism']}")
    lines.append(f"- **人群 / 设计**：{c['population']} ｜ {c['design']}")
    lines.append(f"- **主要结局**：")
    for o in c["primary_outcomes"]:
        note = f"（{o['note']}）" if o.get("note") else ""
        lines.append(f"  - {o['marker']}：{o['change']} {note}")
    lines.append(f"- **效应量**：{c['effect_size']}")
    lines.append(f"- **证据等级**：{c['evidence_level']}")
    lines.append(f"- **基因通路**：{', '.join(c['gene_pathway'])}")
    lines.append(f"- **融合判定链接**：{c['gene_link']}")
    src = c.get("source")
    if isinstance(src, dict):
        ref = src.get("doi") or src.get("pmid") or ""
        lines.append(f"- **来源**：{src.get('journal','')} {src.get('year','')} {('｜ '+ref) if ref else ''}")
    else:
        # 纯文本来源（含 DOI 或「需全文复核」）
        lines.append(f"- **来源**：{src if isinstance(src, str) else ''}")
    lines.append(f"- **理论作证**：{c['fusion_note']}")
    if c["id"] == "CASE-006":
        lines.append("")
        lines.append("> **勘误说明**（2026-10-13）：该案例原误引为「Kirkland AFFIRM 240 人 Phase II RCT，步速握力显著改善」"
                     "（DOI 10.1038/s41591-026-04102-8），经 Crossref 核验该 DOI 不存在、属 AI 幻觉。"
                     "已彻底更正为真实的 Farr 2024 Phase II RCT（Nature Medicine 2024;30(9):2605-2612，DOI 10.1038/s41591-024-03096-2，"
                     "60 名绝经后女性 62–88 岁），并如实描述其 subtle / 中性结局（骨形成标志物早期升高、骨降解无明确改善，未报告功能改善）。")
    lines.append("")

out = ROOT / "data" / "case_evidence_db.md"
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "lines=", len(lines))
