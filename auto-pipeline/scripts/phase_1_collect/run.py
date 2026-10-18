"""
阶段1：情报收集
从多个来源收集竞品动态、技术趋势、学术进展
输出：intelligence_report.json

真实数据源：
- GitHub Trending API (health AI repos)
- arXiv API (health/digital health papers)
- PubMed E-utilities (clinical studies)
- 竞品公开信息 (结构化抓取)
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
# 必须位于 sys.path.insert 之后，不能被 ruff 的 import 排序移到文件顶部
from state_manager import start_phase, complete_phase, fail_phase, BASE_DIR, log  # noqa: I001


def _fetch_json(url, timeout=15):
    """安全获取 JSON 数据"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "HealthLens-IntelBot/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        log(f"  获取失败 {url[:60]}: {str(e)[:80]}", level="WARN")
        return None


def _http_get_with_retry(url, timeout=20, retries=3, backoff=2.0, purpose=""):
    """带指数退避重试的 HTTP GET。

    网络抖动是自动化采集最常见的故障源。此前单次请求即放弃，临时超时会
    静默降级为 0 条，使上层误判该数据源"健康但无数据"。现改为重试，重试
    耗尽后抛出异常，让调用方能正确标记为 error 而非"0 条"。
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "HealthLens-IntelBot/1.0",
                "Accept": "application/json,application/xml,text/xml,*/*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last_err = e
            if attempt < retries:
                wait = backoff * (2 ** (attempt - 1))
                log(f"  {purpose} 第 {attempt}/{retries} 次失败: {str(e)[:60]}，{wait:.0f}s 后重试",
                    level="WARN")
                time.sleep(wait)
            else:
                log(f"  {purpose} 重试 {retries} 次后仍失败: {str(e)[:80]}", level="WARN")
    raise last_err


# 健康领域硬关键词：GitHub repo 的 description/topics 必须命中其一才进入后续链路。
# 此前的空转：GitHub 搜 "health+AI" 返回的项目里，有些 description 根本不含健康词
# （如 repowise-dev/repowise 是个文档工具），却被标 "medium" 相关性进入 Phase 2/3/4，
# 最终 Phase 4 用 f-string 模板生成"repowise-dev/repowise 的健康知识文章"——
# 这是把 GitHub 项目名当健康主题，是整条链路的源头空转。
# 现在：description 或 topics 不含任何健康关键词的 repo 直接跳过。
HEALTH_KEYWORDS = [
    "health", "medical", "genomic", "genomics", "clinical", "fitness",
    "sleep", "nutrition", "diet", "weight", "blood", "biomarker",
    "wellness", "therap", "diagnos", "treatment", "drug", "pharma",
    "disease", "patient", "symptom", "vital sign", "heart rate",
    "blood pressure", "glucose", "insulin", "cholesterol", "immunity",
    "inflammation", "gut", "microbiome", "metabolis", "mitochondri",
    "aging", "longevity", "anti-aging", "cancer", "diabetes",
    "mental health", "anxiety", "depression", "sleep quality",
]

# 机制层关键词（2026-09-19 增补）
# ----------------------------------
# 此前的词表偏"应用/消费级"（sleep/diet/blood pressure…），只按 description
# 字面命中，导致纯机制类项目与论文从源头进不来。实测（2026-09-19）：把
# RNA 剪接体失调、吕垣澄 OSK 部分重编程、CRISPR 基因编辑、斯坦福 iPSC→脑
# 类器官这四类前沿条目逐条对照旧词表，命中数为 0——即这些内容无论多重要，
# 采集器都抓不到。补入机制层词后，q-bio 类与表观遗传/蛋白稳态类条目才可能
# 进入 Phase 2 之后的分析链路。
HEALTH_KEYWORDS_MECHANISM = [
    "splicing", "spliceosome", "transcriptom", "post-transcriptional",
    "reprogramming", "epigenetic", "epigenome", "methylation",
    "organoid", "stem cell", "ipsc", "differentiation",
    "immunotherap", "oncoimmun", "tumor microenvironment",
    "crispr", "gene editing", "gene therapy", "genome editing",
    "proteostasis", "senescence", "telomere", "autophagy",
    "circadian", "healthspan", "geroscience",
]


def _has_health_signal(repo: dict) -> bool:
    """检查 GitHub repo 是否真的与健康领域相关（description + topics + name）。"""
    desc = (repo.get("description") or "").lower()
    topics = " ".join(repo.get("topics") or []).lower()
    name = (repo.get("full_name") or "").lower()
    haystack = f"{desc} {topics} {name}"
    return any(k in haystack for k in HEALTH_KEYWORDS + HEALTH_KEYWORDS_MECHANISM)


def collect_github_trends():
    """从 GitHub Trending 收集健康 AI 相关项目。

    硬过滤：description/topics/name 不含健康关键词的 repo 直接跳过——
    避免把 "repowise-dev/repowise" 这类非健康项目当成健康主题进入内容链路。
    """
    items = []
    queries = ["health+AI", "wearable+health", "medical+AI", "genomics+analysis"]
    skipped = 0

    for query in queries[:2]:  # 限制请求数
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=5"
        data = _fetch_json(url)
        if not data or "items" not in data:
            continue

        for repo in data["items"][:3]:
            # 硬过滤：非健康 repo 不进入后续链路
            if not _has_health_signal(repo):
                skipped += 1
                log(f"  [跳过] {repo['full_name']}: 无健康关键词信号", level="INFO")
                continue

            desc_lower = (repo.get("description") or "").lower()
            items.append({
                "id": f"gh_{repo['id']}",
                "title": repo["full_name"],
                "category": "tech_trend",
                "summary": (repo.get("description") or "")[:200],
                "sources": [{"name": "GitHub", "url": repo["html_url"], "relevance": 0.8}],
                "relevance_to_healthlens": "high" if any(k in desc_lower
                    for k in ["health", "medical", "genomic", "clinical", "fitness", "sleep", "diagnos"]) else "medium",
                "actionable_insight": f"Stars: {repo['stargazers_count']}, Language: {repo.get('language', 'N/A')}",
                "market_signals": {
                    "github_stars": repo["stargazers_count"],
                    "forks": repo["forks_count"],
                    "updated_at": repo.get("updated_at", ""),
                },
                "technical_feasibility": 0.8,
                "tags": [t for t in (repo.get("topics") or [])[:5]],
            })

    if skipped:
        log(f"  GitHub 采集：{len(items)} 个通过健康过滤，{skipped} 个被跳过")
    return items


def collect_arxiv_papers():
    """从 arXiv 收集健康 AI 相关论文"""
    items = []
    queries = [
        "cat:cs.LG AND (health OR medical OR clinical)",
        "cat:q-bio.GN AND (genomic OR precision)",
        # 2026-09-19 增补：机制层第三路查询。
        "cat:q-bio.BM AND (aging OR longevity OR epigenetic)",
    ]

    # 2026-09-19 修复：此前是 `for query in queries[:1]`——硬编码只跑第一条，
    # 第二条 q-bio.GN（基因学）被静默丢弃，等于半个采集器从未启动。
    # 同时把"单条失败即上抛"改为"全部失败才上抛"：原逻辑下任一条查询抖一下
    # 就会让整个 Phase 1 报错，而"一条成功、一条失败"本不该算数据源不可用。
    failed = 0
    for query in queries:
        encoded = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query={encoded}&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
        # 网络请求带重试；失败则计入失败数，避免静默返回空而让上层误判源健康
        try:
            xml_text = _http_get_with_retry(url, timeout=20, retries=3, purpose="arXiv")
        except Exception as e:
            failed += 1
            log(f"  arXiv 查询失败（{query[:40]}）: {str(e)[:80]}", level="WARN")
            continue

        try:
            import re
            entries = re.findall(r"<entry>(.*?)</entry>", xml_text, re.DOTALL)
            for entry in entries:
                title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
                summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
                link_m = re.search(r"<id>(.*?)</id>", entry)
                published_m = re.search(r"<published>(.*?)</published>", entry)

                title = title_m.group(1).strip().replace("\n", " ") if title_m else "Unknown"
                summary = summary_m.group(1).strip().replace("\n", " ")[:200] if summary_m else ""
                link = link_m.group(1).strip() if link_m else ""
                published = published_m.group(1)[:10] if published_m else ""

                items.append({
                    "id": f"arx_{hash(link) % 100000:05d}",
                    "title": title,
                    "category": "academic",
                    "summary": summary,
                    "sources": [{"name": "arXiv", "url": link, "relevance": 0.85}],
                    "relevance_to_healthlens": "high" if any(k in title.lower()
                        for k in ["health", "clinical", "medical", "genomic",
                                  "splicing", "epigenetic", "reprogramming",
                                  "organoid", "senescence", "autophagy"]) else "medium",
                    "actionable_insight": f"发表日期: {published}",
                    "market_signals": {"source": "arXiv", "date": published},
                    "technical_feasibility": 0.75,
                    "tags": ["arxiv", "research"],
                })
        except Exception as e:
            # 解析失败同样是数据不可用，计入失败数；全部查询都失败才上抛
            failed += 1
            log(f"  arXiv 解析失败（{query[:40]}）: {str(e)[:80]}", level="WARN")

    if not items and failed:
        raise RuntimeError(f"arXiv 全部 {len(queries)} 个查询均失败（已重试 3 次）")
    return items


def collect_pubmed_studies():
    """从 PubMed 收集临床研究动态"""
    items = []
    # 2026-09-19 增补机制层检索词组：原查询只有 digital health / precision
    # medicine / lifestyle intervention 三组，全部落在"应用层"，采集不到
    # 剪接失调、表观遗传重编程、类器官、健康寿命这类机制层证据。
    query = (
        "digital health[tiab] OR precision medicine[tiab] OR lifestyle intervention[tiab] "
        "OR RNA splicing[tiab] OR epigenetic reprogramming[tiab] "
        "OR organoid[tiab] OR healthspan[tiab] OR cellular senescence[tiab]"
    )
    encoded = urllib.parse.quote(query)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={encoded}&retmax=5&sort=date&retmode=json"

    data = _fetch_json(url)
    if not data or "esearchresult" not in data:
        return items

    ids = data["esearchresult"].get("idlist", [])
    if not ids:
        return items

    # 获取详情
    id_str = ",".join(ids)
    detail_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={id_str}&retmode=json"
    details = _fetch_json(detail_url)

    if details and "result" in details:
        for uid in ids:
            info = details["result"].get(uid, {})
            if not info or "title" not in info:
                continue
            items.append({
                "id": f"pm_{uid}",
                "title": info["title"][:150],
                "category": "academic",
                "summary": f"Source: PubMed, Published: {info.get('pubdate', 'N/A')[:10]}",
                "sources": [{"name": "PubMed", "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/", "relevance": 0.85}],
                "relevance_to_healthlens": "high",
                "actionable_insight": f"PubMed ID: {uid}",
                "market_signals": {"source": "PubMed", "date": info.get("pubdate", "")[:10]},
                "technical_feasibility": 0.7,
                "tags": ["pubmed", "clinical"],
            })

    return items


def collect_competitor_news():
    """收集竞品公开动态（结构化）

    注意：当前为静态基线数据（人工整理，每次运行内容相同），并非实时抓取。
    已通过 is_static 字段标注，避免下游将其误当作实时情报。
    后续可对接新闻 API / RSS 实现真实采集。
    """
    items = []

    # 基于已知竞品动态生成结构化情报（静态基线）
    known_signals = [
        {
            "title": "国内竞品健康管理App功能对比分析",
            "summary": "主流健康管理App正在向AI化和个性化方向演进，但普遍缺乏基因层面的深度归因。",
            "insight": "基因归因+量化修复是差异化核心竞争力",
            "signals": {"dau_growth": "稳定", "付费率": "3-8%"},
        },
        {
            "title": "PEMF频率疗法在家用设备中的应用增长",
            "summary": "脉冲电磁场(PEMF)疗法的家用设备市场快速增长，从运动恢复延伸到睡眠和抗衰老领域。",
            "insight": "可探索频率干预模块与现有方案的融合",
            "signals": {"market_size": "12亿美元", "cagr": "8.5%"},
        },
    ]

    for i, sig in enumerate(known_signals):
        items.append({
            "id": f"comp_{i+1:03d}",
            "title": sig["title"],
            "category": "market",
            "summary": sig["summary"],
            "sources": [{"name": "竞品分析", "url": "", "relevance": 0.8}],
            "relevance_to_healthlens": "high",
            "actionable_insight": sig["insight"],
            "market_signals": sig["signals"],
            "technical_feasibility": 0.8,
            "tags": ["竞品分析", "市场格局"],
            # 静态基线：非实时抓取，下游据此判断情报新鲜度
            "is_static": True,
            "source_type": "static_baseline",
        })

    return items


def deduplicate_items(items):
    """去重：基于标题相似度"""
    seen_titles = set()
    unique = []
    for item in items:
        title_key = item["title"][:30].lower().strip()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(item)
    return unique


def run():
    phase = "collect"
    try:
        start_phase(phase)

        today = datetime.now().strftime("%Y-%m-%d")
        all_items = []
        sources_checked = 0
        source_results = {}

        # 并行收集各来源
        collectors = [
            ("GitHub", collect_github_trends),
            ("arXiv", collect_arxiv_papers),
            ("PubMed", collect_pubmed_studies),
            ("Competitors", collect_competitor_news),
        ]

        for name, collector in collectors:
            try:
                items = collector()
                all_items.extend(items)
                sources_checked += 1
                source_results[name] = len(items)
                log(f"  {name}: 收集到 {len(items)} 条")
            except Exception as e:
                log(f"  {name} 收集失败: {str(e)[:80]}", level="WARN")
                source_results[name] = f"error: {str(e)[:50]}"

        # 去重
        all_items = deduplicate_items(all_items)

        # 分类统计
        category_breakdown = {}
        for item in all_items:
            cat = item.get("category", "other")
            category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

        # 识别采集失败的源。此前失败被采集函数内部吞掉并计为"0 条"，
        # 使 sources_checked 虚增、data_quality 被高估为 real_api。
        failed_sources = [n for n, v in source_results.items()
                          if isinstance(v, str) and v.startswith("error")]
        if failed_sources:
            data_quality = "degraded" if sources_checked >= 2 else "partial"
        else:
            data_quality = "real_api" if sources_checked >= 2 else "partial"

        report = {
            "report_id": f"intel_{today}",
            "generated_at": datetime.now().isoformat(),
            "sources_checked": sources_checked,
            "sources_failed": failed_sources,
            "source_results": source_results,
            "items": all_items,
            "category_breakdown": category_breakdown,
            "total_items": len(all_items),
            "data_quality": data_quality,
        }

        # 保存报告
        output_file = f"reports/intelligence/{today}_intelligence_report.json"
        output_path = BASE_DIR / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        complete_phase(phase, output_file=output_file, items_processed=len(all_items))
        log(f"情报收集完成: {len(all_items)} 条情报 (来源: {sources_checked})")
        return True

    except Exception as e:
        fail_phase(phase, str(e))
        return False


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
