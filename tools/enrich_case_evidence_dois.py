#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HealthLens 案例库 DOI 富化器 (2026-10-16)

参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §6 §10 #5

任务：把 CASE-001…029 中「有真实文献但 DOI 缺失」的条目补齐真实 DOI。
策略（诚实优先）：
  1. 只对「已知有真实出版物」的条目填 DOI；来源为 Crossref REST API 实检索
     （`api.crossref.org/works?query.title=...`）后人工挑选出的最匹配记录。
  2. 每一个映射到的 DOI 必须用 tools/verify_evidence_dois.py 的 Crossref
     `/works/<doi>` 单条解析二次验证——解析不通的映射直接跳过。
  3. 找不到真实匹配的条目**不编造 DOI**，标 `unverified_no_publication`，
     输出人工检索关键词与提示，让研究者手动补。

输出：
  - 原地更新 data/case_evidence_db.json（新增/覆盖 citation 相关字段）
  - data/case_evidence_db_report_2026-10-16.md（本轮补齐清单 + 未匹配清单）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "case_evidence_db.json")
REPORT_PATH = os.path.join(ROOT, "data", "case_evidence_db_report_2026-10-16.md")
EMAIL = "healthlens-enrich/1.0 (mailto:healthlens-verify@example.com)"

DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s\",}\];）]+")

# ---------------------------------------------------------------------------
# 手工挑选的映射表（每条都经过 Crossref /works/<doi> 单条解析验证）
# 字段：doi, journal, year, title, note
# ---------------------------------------------------------------------------
MAPPING = {
    # CASE-004: 规律运动 → 线粒体生物合成。真实文献：J Appl Physiol 2012
    # "Does SIRT1 determine exercise-induced skeletal muscle mitochondrial
    #  biogenesis..." 该综述直接支持 AMPK/SIRT1/PGC-1α 通路。
    "CASE-004": {
        "doi": "10.1152/japplphysiol.01262.2011",
        "journal": "Journal of Applied Physiology",
        "year": 2012,
        "title": "Does SIRT1 determine exercise-induced skeletal muscle mitochondrial biogenesis: differences between in vitro and in vivo experiments?",
        "note": "综述/机制讨论文献，直接对应 AMPK→SIRT1→PGC-1α 轴；"
                "对应用例标注的运动/线粒体生物合成机制。",
    },
    # CASE-005: D+Q senolytics。真实文献：Hickson 2019 EBioMedicine
    # 已在原 source 文本中提及，本轮把 DOI 抽取到结构化字段。
    "CASE-005": {
        "doi": "10.1016/j.ebiom.2019.08.069",
        "journal": "EBioMedicine",
        "year": 2019,
        "title": "Senolytics decrease senescent cells in humans: Preliminary report from a clinical trial of Dasatinib plus Quercetin in individuals with diabetic kidney disease",
        "note": "Hickson 2019 D+Q 首次人体 senolytic 试验；"
                "支持 CASE-005 表述的『衰老细胞负荷下降』效应量。",
    },
    # CASE-007: Early vs Late TRE 12-week RCT。DOI 已在原 source 文本提及，
    # 但源结构为 str；本轮抽到结构化字段。
    "CASE-007": {
        "doi": "10.1038/s41591-024-03375-y",
        "journal": "Nature Medicine",
        "year": 2025,
        "title": "Effects of early, late and self-selected time-restricted eating on weight loss and other metabolic parameters in adults with obesity: the TREND randomized clinical trial",
        "note": "Dote-Montero 2025 TREND 试验；支持 CASE-007 early TRE 优效结论。",
    },
    # CASE-008: 16:8 TRE 4 个月肝脂 RCT。DOI 已在原 source 文本提及。
    "CASE-008": {
        "doi": "10.1016/j.jhep.2025.06.005",
        "journal": "Journal of Hepatology",
        "year": 2025,
        "title": "Efficacy and safety of time-restricted eating in metabolic dysfunction-associated steatotic liver disease: a randomized clinical trial",
        "note": "Oh 2025 J Hepatol RCT；支持 CASE-008 TRE liver fat↓25.8% 效应量。",
    },
    # CASE-011: 太极 HRV。真实文献：Complementary Therapies in Clinical Practice
    # 2016 meta 分析，直接测量 HRV。
    "CASE-011": {
        "doi": "10.1016/j.ctcp.2016.03.007",
        "journal": "Complementary Therapies in Clinical Practice",
        "year": 2016,
        "title": "Effects of Tai Chi exercise on heart rate variability: A systematic review and meta-analysis",
        "note": "太极/HRV meta 分析；直接支持 CASE-011 HRV 提升结论。",
    },
    # CASE-012: 冥想 HRV。原候选 Mrazek 2012 JAHA 在 Crossref 中未解析成功
    # (可能 DOI 变更或 Crossref 缺录)；未强行编造替换，标为未匹配。
    # 若研究者后续在 PubMed 找到 Mrazek 2012 的规范 DOI 可用同一流程回填。
    # CASE-024 (第一条 duplicate): 电针足三里 ST36 抗炎。真实文献：
    # Nature Biotechnology 2026 RUSH3D-HR 介观共聚焦体积显微镜研究。
    # 与 CASE-024 原 source 描述完全对应（王伟 × 戴琼海）。
    "CASE-024-ACU": {
        "doi": "10.1038/s41587-026-03231-z",
        "journal": "Nature Biotechnology",
        "year": 2026,
        "title": "High numerical aperture confocal volumetric mesoscope reveals mesoscale subcellular dynamics in vivo",
        "note": "RUSH3D-HR 介观共聚焦显微镜活体成像；首次可视化电针抗炎的"
                "中性粒细胞群聚事件（群聚频率炎症态~10×，电针后↓>5×）。",
    },
    # CASE-029: Exercise-induced exosomes。原 source 文本已提及 DOI。
    "CASE-029": {
        "doi": "10.1186/s12967-026-08038-9",
        "journal": "Journal of Translational Medicine",
        "year": 2026,
        "title": "Exercise-induced muscle exosomes: microRNA cargo as regulators of inter-tissue crosstalk",
        "note": "Yu 2026 J Transl Med；支持 CASE-029 运动外泌体 miR-133a 结论。",
    },
}

# ---------------------------------------------------------------------------
# Crossref 二次验证：对每个候选 DOI 走 /works/<doi> 单条解析
# ---------------------------------------------------------------------------


def crossref_resolve(doi: str) -> tuple[str, dict]:
    """返回 (status, meta)。status ∈ found | not_found | error。"""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "20", "--ssl-no-revoke", "--tlsv1.3",
             "-A", EMAIL, "-w", "\n%{http_code}", url],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return "error", {"error": str(e)}
    if proc.returncode != 0:
        return "error", {"error": f"curl rc={proc.returncode}"}
    lines = proc.stdout.strip().rsplit("\n", 1)
    body = lines[0].strip()
    http_code = lines[1].strip() if len(lines) > 1 else ""
    if http_code == "404" or "Resource not found" in body:
        return "not_found", {}
    if not body:
        return "error", {"error": "empty body"}
    try:
        j = json.loads(body)
    except Exception:  # noqa: BLE001
        return "error", {"error": "bad json"}
    if j.get("status") != "ok":
        return "not_found", {}
    msg = j.get("message", {})
    title = (msg.get("title") or [""])[0]
    container = msg.get("container-title") or []
    journal = container[0] if container else ""
    pub = msg.get("publisher", "")
    year = ""
    for key in ("published", "published-print", "issued"):
        parts = (msg.get(key) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    return "found", {"title": title, "journal": journal, "year": year, "publisher": pub}


# ---------------------------------------------------------------------------
# 富化主流程
# ---------------------------------------------------------------------------


def find_case_id(case: dict) -> str | None:
    """兼容两种 schema：CASE-xxx (dict source) / HL-xxxx (synthetic)."""
    return case.get("case_id") or case.get("id")


def case_key(case: dict) -> str:
    """给每个 case 生成映射键；CASE-024 因存在两条重复记录需区分。"""
    cid = find_case_id(case) or ""
    if cid == "CASE-024":
        iv = (case.get("intervention") or "")
        if "外泌体" in iv or "exosome" in iv.lower():
            return "CASE-024-EXO"
        return "CASE-024-ACU"
    return cid


def build_search_keywords(case: dict) -> list[str]:
    """为无法自动匹配的 case 生成人工检索关键词（写入报告）。"""
    parts: list[str] = []
    for f in ("intervention", "tcm_concept", "mechanism"):
        v = case.get(f)
        if v and isinstance(v, str):
            parts.append(v)
    for o in (case.get("primary_outcomes") or [])[:3]:
        if isinstance(o, dict) and o.get("marker"):
            parts.append(str(o["marker"]))
    parts.extend(o for o in (case.get("gene_pathway") or [])
                 if isinstance(o, str))
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return seen[:8]


def run() -> int:
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    print(f"[load] {DB_PATH} -> {len(db['cases'])} cases")

    # Step 1: 先离线验证映射表中的每个 DOI 是否真实可解析
    print("[verify] resolving candidate DOIs via Crossref /works/<doi> ...")
    verified_map: dict[str, dict] = {}
    for k, m in MAPPING.items():
        doi = m["doi"]
        if not DOI_RE.match(doi):
            print(f"  [skip] {k} -> DOI format invalid: {doi}")
            continue
        status, meta = crossref_resolve(doi)
        time.sleep(0.25)
        if status != "found":
            print(f"  [FAIL] {k} -> {doi} status={status} ({meta})")
            continue
        verified_map[k] = {
            **m,
            "crossref_meta": meta,
        }
        print(f"  [ok]   {k} -> {doi} ({meta.get('journal','?')} {meta.get('year','?')})")

    # Step 2: 富化 case
    n_added = n_kept = n_flagged = n_synthetic = n_traditional = 0
    unmatched_for_report: list[dict] = []
    for c in db["cases"]:
        key = case_key(c)
        iv = (c.get("intervention") or "")
        if key in ("HL-",) or str(key).startswith("HL-"):
            # 验证夹具：不是文献案例，标 synthetic（无 DOI 合理）
            c["citation_status"] = "synthetic_validation"
            c["doi_verified"] = False
            c["disclaimer"] = ("此条目为按低分轴自动生成的验证夹具，非文献案例；"
                              "effect_size 由内部模型合成，不直接可引用至单一出版物。")
            n_synthetic += 1
            continue

        # 传统食疗条目（CASE-014…021）：不追求 DOI
        if c.get("citation_status") == "traditional":
            c["disclaimer"] = ("传统中医食疗条目，来源为古籍与本草学文献；"
                              "不做现代 DOI 化，保留古籍证据等级 L3。")
            n_traditional += 1
            continue

        m = verified_map.get(key)
        if m is None:
            # 未匹配：标 unverified_no_publication + 检索关键词
            c["citation_status"] = "unverified_no_publication"
            c["doi_verified"] = False
            # 若原 doi 字段是自由文本（非真实 DOI 格式），迁移到 doi_candidate_note
            old_doi = c.get("doi")
            if old_doi and old_doi != "traditional":
                if not (isinstance(old_doi, str) and DOI_RE.match(old_doi)):
                    # 非真实 DOI：把自由文本搬到 note，清空 doi 字段
                    c["doi_candidate_note"] = old_doi
                    c["doi"] = None
                # 若已经是合法 DOI 格式但无法确认（例如解析 404），也标记
                elif c.get("citation_status") in ("broken_citation",):
                    pass  # 保留 doi 供排查
            # 保留既有 effect_size，追加 disclaimer
            c["disclaimer"] = ("Effect size synthesized from internal model, not "
                              "directly citable to a single publication.")
            if not c.get("search_keywords"):
                c["search_keywords"] = build_search_keywords(c)
            unmatched_for_report.append({
                "case_id": key,
                "intervention": iv[:80],
                "search_keywords": c["search_keywords"],
                "effect_size": (c.get("effect_size") or "")[:120],
                "original_source": c.get("source"),
            })
            n_flagged += 1
            continue

        # 匹配成功：写入真实 DOI
        c["doi"] = m["doi"]
        c["doi_verified"] = True
        c["citation_status"] = "verified_crossref"
        c["source_canonical"] = {
            "title": m["crossref_meta"].get("title", m["title"]),
            "journal": m["crossref_meta"].get("journal", m["journal"]),
            "year": m["crossref_meta"].get("year", str(m["year"])),
            "publisher": m["crossref_meta"].get("publisher", ""),
        }
        c["enrichment_note"] = m["note"]
        # 若原 source 是纯字符串，升级为结构化 dict（保留原文本作为 note）
        old_src = c.get("source")
        if isinstance(old_src, str):
            c["source"] = {
                "title": m["crossref_meta"].get("title", m["title"]),
                "journal": m["journal"],
                "year": m["year"],
                "doi": m["doi"],
                "note": f"原 source 文本（人工复核用）：{old_src[:200]}",
            }
        n_added += 1

    # Step 3: 汇总 & 更新元数据
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"[write] updated -> {DB_PATH}")
    print(f"[done] added={n_added} flagged={n_flagged} synthetic={n_synthetic} traditional={n_traditional}")

    # Step 4: 写报告
    lines = [
        "# HealthLens 案例库 DOI 富化报告（2026-10-16）",
        "",
        "> 参考章节：`HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md` §6（前瞻性队列 + ",
        "> 预注册）与 §10 #5（案例库剩余 95 条补 DOI）。上一轮基线：",
        "> `data/DOI_VERIFICATION_REPORT_2026-10-13.md`。",
        "",
        "**核验方法**：所有新写入的 DOI 均通过 Crossref REST API ",
        "`/works/<doi>` 单条解析二次验证（HTTP 200 + `status=ok` 才接受）。",
        "",
        "## 一、本轮结果",
        "",
        f"- 案例总数：**{len(db['cases'])}**",
        f"- ✅ 本轮新增 verified_crossref：**{n_added}**（新增/规范化 DOI）",
        f"- 📜 传统食疗条目（保留 traditional，不需 DOI）：**{n_traditional}**",
        f"- 🤖 验证夹具（保留 synthetic_validation）：**{n_synthetic}**",
        f"- ⚠️ 未匹配文献（unverified_no_publication）：**{n_flagged}**",
        "",
        "## 二、本轮新增 verified_crossref 清单",
        "",
        "| Case | DOI | 期刊 | 年 | 标题 |",
        "|---|---|---|---|---|",
    ]
    for c in db["cases"]:
        if c.get("citation_status") == "verified_crossref" and c.get("enrichment_note"):
            cid = find_case_id(c)
            sc = c.get("source_canonical", {})
            lines.append(f"| {cid} | `{c.get('doi')}` | {sc.get('journal','')} "
                         f"| {sc.get('year','')} | {str(sc.get('title',''))[:80]} |")
    lines.append("")
    lines.append("## 三、已 verified 但未走本轮 enrichment（先前工具确认，本轮保留）")
    lines.append("")
    lines.append("| Case | DOI | 期刊 | 年 |")
    lines.append("|---|---|---|---|")
    for c in db["cases"]:
        if c.get("citation_status") == "verified" and not c.get("enrichment_note"):
            cid = find_case_id(c)
            sc = c.get("source_canonical", {})
            lines.append(f"| {cid} | `{c.get('doi','')}` | {sc.get('journal','')} | {sc.get('year','')} |")
    lines.append("")

    lines.append("## 四、未匹配案例（需人工介入）")
    lines.append("")
    lines.append("> 以下条目**未强行编造 DOI**。每条附检索关键词供 PubMed / "
                 "Crossref 手工检索；如找到真实出版物，请以与本次一致的方法")
    lines.append("> 补齐（写 DOI → 用 `tools/verify_evidence_dois.py` 反查 → 更新本表）。")
    lines.append("")
    for entry in unmatched_for_report:
        lines.append(f"### {entry['case_id']}")
        lines.append(f"- **干预**：{entry['intervention']}")
        lines.append(f"- **原 source**：`{entry['original_source']}`")
        lines.append(f"- **effect_size**：{entry['effect_size']}")
        lines.append(f"- **检索关键词**：")
        for kw in entry["search_keywords"]:
            lines.append(f"  - `{kw}`")
        lines.append("")
    lines.append("## 五、验证夹具与食疗条目（本轮不做 DOI 化）")
    lines.append("")
    lines.append(f"- **验证夹具**（HL-0030…HL-0120，共 {n_synthetic} 条）："
                 "由低分轴自动生成，设计上非文献案例；不做 DOI 匹配。")
    lines.append(f"- **传统食疗**（CASE-014…021，共 {n_traditional} 条）："
                 "来源为古籍/本草，保留 traditional 状态与 L3 证据等级。")
    lines.append("")
    lines.append("> **诚实披露**：'案例库 DOI 覆盖率'当前真实值 = "
                 f"{n_added + sum(1 for c in db['cases'] if c.get('citation_status')=='verified')}"
                 f"/120。报告 §10 #5 目标 95% 在当前混合 schema 下不可诚实达成；")
    lines.append("> 需将『真实文献案例』与『自动生成验证夹具』分区后再做覆盖率统计。")
    lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[done] report -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
