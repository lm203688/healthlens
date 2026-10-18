#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HealthLens 证据层 DOI 核验器 (S0-5 / S1-1)
============================================
对 data/case_evidence_db.json 中的全部 DOI 做 Crossref 实解析，
不臆造、不补造：能解析的标 verified，解析不了的如实标记。

- 真实可解析 DOI -> citation_status="verified"，写入规范化的 doi / canonical 元数据
- 纯文本来源（无 DOI 或待复核）-> "unverified_text"
- 古籍 / 传统文献（无需 DOI）   -> "traditional"
- 完全无来源                   -> "unsourced"
- 已知幻觉 DOI（10.1038/s41591-026-04102-8）-> 替换为真实 Farr 2024 并标 verified

输出：
  data/doi_verification_results.json
  data/DOI_VERIFICATION_REPORT_2026-10-13.md
  （原地回写 case_evidence_db.json 的 citation 字段）
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "case_evidence_db.json")
RESULTS_PATH = os.path.join(ROOT, "data", "doi_verification_results.json")
REPORT_PATH = os.path.join(ROOT, "data", "DOI_VERIFICATION_REPORT_2026-10-13.md")

# 已知幻觉 DOI -> 真实可解析替代（Farr 2024 真实 senolytic Phase II RCT，Crossref 已验证）
HALLUCINATED = {
    "10.1038/s41591-026-04102-8": {
        "doi": "10.1038/s41591-024-03096-2",
        "note": "原 'Kirkland Nature Medicine 2026 AFFIRM' 为 AI 幻觉（DOI 不存在、240人/65-85/步速改善均不实）。"
                "替换为真实 Farr 2024 Phase II RCT（60 名绝经后女性 62-88 岁，骨代谢，结果 subtle）。",
    }
}

EMAIL = "healthlens-verify@example.com"  # Crossref polite pool
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\",}\];）+]+")
POLITE_DELAY = 0.25


def crossref_query(doi):
    """返回 (status, meta_dict)。status ∈ found | not_found | error"""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "20", "--ssl-no-revoke", "--tlsv1.3",
             "-A", f"healthlens-verify/1.0 (mailto:{EMAIL})", "-w", "\n%{http_code}",
             url],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:  # noqa
        return "error", {"error": str(e)}
    if proc.returncode != 0:
        return "error", {"error": f"curl rc={proc.returncode}"}
    out = proc.stdout.strip()
    # 末行是 HTTP 状态码
    lines = out.rsplit("\n", 1)
    body = lines[0].strip()
    http_code = lines[1].strip() if len(lines) > 1 else ""
    if http_code == "404" or "Resource not found" in body:
        return "not_found", {}
    if not body:
        return "error", {"error": "empty body"}
    try:
        j = json.loads(body)
    except Exception:
        return "error", {"error": "bad json"}
    if j.get("status") != "ok":
        return "not_found", {}
    msg = j.get("message", {})
    title = (msg.get("title") or [""])[0]
    container = msg.get("container-title") or msg.get("institution") or [""]
    journal = container[0] if isinstance(container, list) else container
    pub = msg.get("publisher", "")
    # 出版年
    year = ""
    for key in ("published", "published-print", "issued"):
        parts = (msg.get(key) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    return "found", {
        "title": title,
        "journal": journal,
        "year": year,
        "publisher": pub,
        "type": msg.get("type", ""),
    }


def _clean_doi(raw):
    """去掉尾随标点（含中文全角括号/标点），只保留 ASCII DOI 主体"""
    s = raw.strip().rstrip(";.,）)】]")
    # 截掉第一个非 ASCII 字符及其之后（DOI 应为纯 ASCII）
    for i, ch in enumerate(s):
        if ord(ch) > 127:
            s = s[:i]
            break
    return s.strip()


def collect_dois(db):
    """从 case 全字段收集所有 DOI 字符串（去尾标点）"""
    dois = set()
    for c in db["cases"]:
        src = c.get("source")
        if isinstance(src, dict) and src.get("doi"):
            d = _clean_doi(src["doi"])
            if d and re.match(r"^10\.\d{4,9}/", d):
                dois.add(d)
        blob = json.dumps(c, ensure_ascii=False)
        for m in DOI_RE.findall(blob):
            d = _clean_doi(m)
            if d and re.match(r"^10\.\d{4,9}/", d):
                dois.add(d)
    return sorted(dois)


def main():
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    all_dois = collect_dois(db)
    print(f"[collect] {len(all_dois)} distinct DOI-like strings in case DB")

    # 解析所有 DOI（带缓存落盘避免重复打）
    cache = {}
    if os.path.exists(RESULTS_PATH):
        try:
            cache = json.load(open(RESULTS_PATH, encoding="utf-8")).get("_crossref_cache", {})
        except Exception:
            cache = {}

    results = {}
    for doi in all_dois:
        if doi in cache:
            results[doi] = cache[doi]
            continue
        status, meta = crossref_query(doi)
        # 幻觉 DOI：不直接标 found，记其替代
        if doi in HALLUCINATED:
            repl = HALLUCINATED[doi]["doi"]
            rstat, rmeta = crossref_query(repl)
            results[doi] = {
                "status": "hallucinated",
                "replaced_by": repl,
                "replacement_status": rstat,
                "replacement_meta": rmeta,
                "note": HALLUCINATED[doi]["note"],
            }
        else:
            results[doi] = {"status": status, **meta}
        cache[doi] = results[doi]
        time.sleep(POLITE_DELAY)

    # 回写 case 级 citation 字段
    n_verified = n_unverified = n_traditional = n_unsourced = n_resolved = n_synthetic = n_broken = 0
    for c in db["cases"]:
        src = c.get("source")
        citation_status = None
        doi_verified = False
        doi_final = None
        canonical = None

        # 先扫全字段是否含已知幻觉 DOI（无论 source 是 dict 还是 string）
        blob = json.dumps(c, ensure_ascii=False)
        hit_hallucination = None
        for hdoi in HALLUCINATED:
            if hdoi in blob:
                hit_hallucination = hdoi
                break

        if hit_hallucination:
            repl = HALLUCINATED[hit_hallucination]["doi"]
            hinfo = results.get(hit_hallucination)
            if not hinfo or hinfo.get("replacement_status") is None:
                rstat, rmeta = crossref_query(repl)
                results[hit_hallucination] = {
                    "status": "hallucinated", "replaced_by": repl,
                    "replacement_status": rstat, "replacement_meta": rmeta,
                    "note": HALLUCINATED[hit_hallucination]["note"],
                }
                cache[hit_hallucination] = results[hit_hallucination]
            rstat = results[hit_hallucination].get("replacement_status", "error")
            rmeta = results[hit_hallucination].get("replacement_meta", {})
            citation_status = "verified" if rstat == "found" else "unverified_text"
            doi_verified = (rstat == "found")
            doi_final = repl
            canonical = rmeta
            if rstat == "found":
                n_resolved += 1
            else:
                n_unverified += 1
            # 同时把幻觉事实字段改写成真实 Farr 2024 研究结果（诚实，不夸功能改善）
            c["intervention"] = "D+Q (dasatinib+quercetin) 间歇性 senolytic 给药 — Farr 2024 Phase II RCT"
            c["population"] = "60 名绝经后女性，年龄 62-88 岁"
            c["design"] = "Phase II RCT，12 个月（Mayo Clinic）"
            c["mechanism"] = "衰老细胞清除 → 骨代谢调节（真实结果：骨形成标志物早期升高、骨降解无明确改善）"
            c["primary_outcomes"] = [
                {"marker": "骨形成标志物 P1NP", "change": "早期时间点升高", "note": "bone formation marker"},
                {"marker": "骨降解标志物 CTX", "change": "无明确改善", "note": "bone degradation marker"},
            ]
            c["effect_size"] = ("骨形成标志物早期升高、骨降解无明确改善（结果 subtle，假设生成性）；"
                                "真实研究未报告步速/握力等功能改善。")
            c["source"] = {
                "authors": "Farr JN, Atkinson EJ, Khosla S, et al.",
                "title": "Effects of intermittent senolytic therapy on bone metabolism in postmenopausal women: a phase 2 randomized controlled trial",
                "journal": "Nature Medicine",
                "year": 2024,
                "doi": repl,
                "note": "原幻觉 DOI 10.1038/s41591-026-04102-8（'AFFIRM' 试验）已替换为真实 Phase II RCT；"
                        "真实结果为骨形成标志物早期升高、骨降解无明确改善（subtle），非功能改善。",
            }
            c["fusion_note"] = ("把'衰老/肾虚'落到可测量骨代谢结局；H 轴功能代理证据。"
                                "注意：真实 Farr 2024 结果为 subtle，仅假设生成性，不应夸大功能获益。")
            c["citation_status"] = citation_status
            c["doi_verified"] = doi_verified
            c["doi"] = doi_final
            if canonical:
                c["source_canonical"] = {k: canonical.get(k) for k in ("title", "journal", "year", "publisher")}
            continue

        # 结构化 source（dict）
        if isinstance(src, dict):
            d = (src.get("doi") or "").strip().rstrip(";.")
            if d:
                if d.lower() in ("traditional", "古籍"):
                    citation_status = "traditional"
                    n_traditional += 1
                elif d in HALLUCINATED:
                    repl = HALLUCINATED[d]["doi"]
                    citation_status = "verified"
                    doi_verified = True
                    doi_final = repl
                    canonical = results[d].get("replacement_meta", {})
                    n_resolved += 1
                    # 修正 source 文本
                    c["source"] = {
                        "authors": "Farr JN, Atkinson EJ, Khosla S, et al.",
                        "title": "Effects of intermittent senolytic therapy on bone metabolism in postmenopausal women: a phase 2 randomized controlled trial",
                        "journal": "Nature Medicine",
                        "year": 2024,
                        "doi": repl,
                        "note": "原幻觉 DOI 已替换为真实 Phase II RCT；真实结果为骨形成标志物早期升高、骨降解无明确改善（subtle）。",
                    }
                elif results.get(d, {}).get("status") == "found":
                    citation_status = "verified"
                    doi_verified = True
                    doi_final = d
                    canonical = {k: results[d].get(k) for k in ("title", "journal", "year", "publisher")}
                    n_verified += 1
                else:
                    citation_status = "unverified_text"
                    doi_final = d
                    n_unverified += 1
            else:
                citation_status = "unverified_text"
                n_unverified += 1
        elif isinstance(src, str) and src.strip():
            # 扫描文本中的 DOI，若含 not_found / hallucinated 则标记为失效引用
            text_dois = [_clean_doi(m) for m in DOI_RE.findall(src)]
            text_dois = [d for d in text_dois if re.match(r"^10\.\d{4,9}/", d)]
            broken = [d for d in text_dois
                      if results.get(d, {}).get("status") in ("not_found", "hallucinated")]
            if broken:
                citation_status = "broken_citation"
                n_broken += 1
                doi_final = broken[0]
            elif src.strip().lower() in ("traditional", "古籍", ""):
                citation_status = "traditional"
                n_traditional += 1
            else:
                citation_status = "unverified_text"
                n_unverified += 1
        else:
            # HL- 前缀的验证案例是自动生成的验证夹具（无文献来源，设计如此）
            if str(c.get("case_id", "")).startswith("HL-"):
                citation_status = "synthetic_validation"
                n_synthetic += 1
            else:
                citation_status = "unsourced"
                n_unsourced += 1

        c["citation_status"] = citation_status
        c["doi_verified"] = doi_verified
        if doi_final:
            c["doi"] = doi_final
        if canonical:
            c["source_canonical"] = canonical

    # 写回 DB
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    # 汇总
    summary = {
        "total_cases": len(db["cases"]),
        "verified": n_verified,
        "hallucination_resolved": n_resolved,
        "unverified_text": n_unverified,
        "traditional": n_traditional,
        "unsourced": n_unsourced,
        "broken_citation": n_broken,
        "synthetic_validation": n_synthetic,
        "distinct_dois_checked": len(all_dois),
        "doi_resolution": {d: results[d]["status"] for d in all_dois},
    }

    out = {
        "generated_at": time.strftime("%Y-%m-%d"),
        "summary": summary,
        "crossref_details": results,
        "_crossref_cache": cache,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Markdown 报告
    lines = []
    lines.append("# HealthLens 案例库 DOI 核验报告（2026-10-13）\n")
    lines.append("**核验方法**：Crossref REST API 实解析（`api.crossref.org/works/<doi>`），不臆造 DOI。\n")
    lines.append("## 一、总体覆盖\n")
    lines.append(f"- 案例总数：**{summary['total_cases']}**")
    lines.append(f"- ✅ 已验证可解析（含幻觉已替换）：**{summary['verified'] + summary['hallucination_resolved']}**")
    lines.append(f"- 🔁 幻觉 DOI 已替换为真文献：**{summary['hallucination_resolved']}**（CASE-006）")
    lines.append(f"- ⚠️ 纯文本来源待复核（无 DOI 或需全文复核）：**{summary['unverified_text']}**")
    lines.append(f"- 📜 古籍/传统文献（无需 DOI）：**{summary['traditional']}**")
    lines.append(f"- 💀 失效引用（DOI 解析 404 / 幻觉）：**{summary['broken_citation']}**")
    lines.append(f"- 🤖 自动生成验证夹具（设计上无文献来源）：**{summary['synthetic_validation']}**")
    lines.append(f"- ❌ 完全无来源：**{summary['unsourced']}**")
    lines.append("")
    lines.append("> **诚实说明（数据完整性关键）**：案例库 120 条实为**两种 schema 的混合**——"
                 "前 29 条（CASE-001…029）是带文献来源的证据案例；"
                 "后 91 条（HL-0030…0120）是**按低分轴自动生成的验证夹具**（`case_id`/`symptom`/`tcm_source` 模式），"
                 "设计上即无一手文献来源，并非「真实人体试验/RCT」。"
                 "meta 中「用真实人体试验/RCT 数据作证」的声明仅适用于前 29 条。"
                 "本报告**未对无来源的条目臆造 DOI**——S1-1「覆盖率≥95%」在当前真实数据下无法诚实达成，"
                 "需后续真实回填纵向数据或将验证夹具与证据案例明确分区。\n")
    lines.append("## 二、逐 DOI 解析结果\n")
    lines.append("| DOI | 状态 | 期刊 | 年 | 标题 |")
    lines.append("|---|---|---|---|---|")
    for d in all_dois:
        r = results[d]
        if r.get("status") == "hallucinated":
            repl = r.get("replacement_meta", {})
            lines.append(f"| `{d}` | 🔁幻觉→`{r['replaced_by']}` | {repl.get('journal','')} | {repl.get('year','')} | {repl.get('title','')[:60]} |")
        elif r.get("status") == "found":
            lines.append(f"| `{d}` | ✅ | {r.get('journal','')} | {r.get('year','')} | {str(r.get('title',''))[:60]} |")
        else:
            lines.append(f"| `{d}` | ❌{r.get('status')} | | | |")
    lines.append("")
    lines.append("## 三、案例级 citation_status 分布（见 case_evidence_db.json 各 case 字段）\n")
    lines.append("每个案例现含 `citation_status` / `doi_verified` / `doi` / `source_canonical` 字段，供下游 fusion_engine 与 Agent 引用时区分证据强度。\n")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[done] verified={n_verified} resolved={n_resolved} unverified_text={n_unverified} traditional={n_traditional} unsourced={n_unsourced}")
    print(f"[done] DB patched -> {DB_PATH}")
    print(f"[done] report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
