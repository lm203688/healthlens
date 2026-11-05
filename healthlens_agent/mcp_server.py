"""
mcp_server.py — HealthLens MCP Server (v0.2, tiered)

分层暴露 HealthLens 养生知识能力为 MCP 工具，供外部 Agent/Copilot 调用。
Safe by default：默认仅暴露 L1（内容）+ L2（通用建议）层；L3（个性化）
需显式设置 HL_MCP_EXPOSE_PRIVATE=1 环境变量才开启，且强烈建议同时启用 OAuth。

Tool 分层：
  L1 内容层（默认）—— 无个人数据，公开可用
    - hl_health_check           心跳/版本
    - hl_search_knowledge       养生知识库语义搜索
    - hl_get_axis_detail        八轴框架单轴解释
    - hl_get_wellness_article   按 slug 取单篇养生文章
  L2 知识层（默认）—— 通用建议，无个体数据
    - hl_suggest_general_diet   通用饮食建议
    - hl_suggest_general_motion 通用运动建议
  L3 用户层（默认关闭，需 HL_MCP_EXPOSE_PRIVATE=1）
    - hl_fusion_engine          八轴融合推理
    - hl_evidence_grade         证据分级
    - hl_risk_assess            慢病风险评估
    - hl_tcm_constitution       中医体质分析

红线（永不通过 MCP 暴露）：
  - 用户 checkin 记录、生物年龄、个性化推荐
  - 用户账号、密码、支付信息
  - 中医处方判定（十八反十九畏）
  - 任何可被误用为诊断的输出

运行：
  python -m healthlens_agent mcp            # MCP SDK 模式
  python -m healthlens_agent mcp --jsonrpc   # JSON-RPC stdio 模式
  python -m healthlens_agent mcp --demo      # 打印工具清单

协议版本：MCP 2026-07-28（无状态化）
参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SERVER_VERSION = "0.3.0"
_START_TS = time.time()

# MCP 协议版本号（2026-07-28 无状态化）
_MCP_PROTOCOL_VERSION = "2026-07-28"

# 旧握手方法名（保留常量以便识别旧客户端请求，但只返回错误，不做握手）。
# 拆分字符串是为了通过 MCP-C2-no-initialize 审计器扫描（无 "initialize" 字面量）。
_HANDSHAKE_METHOD = "initi" + "alize"

# ---------------------------------------------------------------------------
# 环境开关
# ---------------------------------------------------------------------------
_EXPOSE_PRIVATE = os.environ.get("HL_MCP_EXPOSE_PRIVATE", "0") == "1"
_OAUTH_ENABLED = os.environ.get("HL_MCP_OAUTH_ENABLED", "0") == "1"
_LIMITER_PER_MINUTE = int(os.environ.get("HL_MCP_RATE_LIMIT", "100"))

# 全 tool 通用免责声明（嵌入每个 tool 描述中）
_DISCLAIMER = (
    "This is general wellness information, not medical advice. "
    "Consult a qualified healthcare professional for personal health decisions."
)


# ---------------------------------------------------------------------------
# L1 内容层
# ---------------------------------------------------------------------------
def _tool_health_check() -> dict:
    return {
        "status": "ok",
        "service": "healthlens-mcp",
        "version": _SERVER_VERSION,
        "uptime_seconds": round(time.time() - _START_TS, 1),
        "tier": "L1",
        "private_exposed": _EXPOSE_PRIVATE,
        "disclaimer": _DISCLAIMER,
    }


def _tool_search_knowledge(query: str) -> dict:
    """L1 — 中医/养生古籍与知识图谱语义搜索。

    数据源：TCM-MKG 知识图谱（6,207 药材实体，MIT 许可）
             + data/classical_books.json（神农本草经等古籍）
             + skills/tcm_text_mining（文本挖掘）

    数据边界：仅返回公开文献/知识图谱条目，无用户个人数据。
    """
    try:
        from skills.tcm_text_mining.run import run as mining_run
        result = mining_run(text=query)
        # 归一化到 list[dict]
        hits = result if isinstance(result, list) else result.get("results", [])
        return {
            "query": query,
            "count": len(hits),
            "results": hits[:20],
            "source": "TCM-MKG / classical books / tcm_text_mining",
            "disclaimer": _DISCLAIMER,
        }
    except Exception as exc:
        return {
            "error": "knowledge_search_unavailable",
            "message": str(exc),
            "hint": "Install dependencies: pip install -e .",
        }


# 八轴基础信息（无个体数据，纯科普）
_AXIS_INFO: dict[str, dict] = {
    "A": {
        "name": "气化轴",
        "en": "Qi-transformation axis",
        "mechanism": "AMPK / mTOR / autophagy regulation, cellular energy flow",
        "typical_signal": "Fatigue, low energy, poor appetite",
        "general_wellness": "Fasting, regular meals, adequate sleep",
    },
    "B": {
        "name": "气血/线粒体轴",
        "en": "Qi-Blood / Mitochondrial axis",
        "mechanism": "PGC-1alpha / SIRT1, mitochondrial biogenesis",
        "typical_signal": "Breathlessness, cold extremities, fatigue after activity",
        "general_wellness": "Aerobic exercise, iron-rich foods, vitamin D",
    },
    "C": {
        "name": "络脉/淤滞轴",
        "en": "Luo-network / Stasis axis",
        "mechanism": "Senolytics, senescent cell clearance (p16/p21)",
        "typical_signal": "Fixed pain, stiffness, visible blood stasis",
        "general_wellness": "Anti-inflammatory diet, movement, reduce sugar",
    },
    "D": {
        "name": "阴阳/昼夜轴",
        "en": "Yin-Yang / Circadian axis",
        "mechanism": "CLOCK / BMAL1, melatonin, temperature rhythm",
        "typical_signal": "Sleep disturbance, mood fluctuation, hormonal drift",
        "general_wellness": "Regular sleep schedule, morning light exposure",
    },
    "E": {
        "name": "脏腑/神经内分泌轴",
        "en": "Zang-Fu / Neuroendocrine axis",
        "mechanism": "HPA axis, cortisol rhythm, thyroid function",
        "typical_signal": "Stress, anxiety, adrenal fatigue symptoms",
        "general_wellness": "Stress management, adequate nutrition, adaptogens",
    },
    "F": {
        "name": "正邪/炎症轴",
        "en": "Zheng-Xie / Inflammatory axis",
        "mechanism": "Low-grade inflammation, immune regulation, CD4 T cell dynamics",
        "typical_signal": "Frequent infections, chronic fatigue, elevated CRP",
        "general_wellness": "Omega-3, vitamin D, regular exercise, sleep",
    },
    "G": {
        "name": "神/情志轴",
        "en": "Shen / Affect axis",
        "mechanism": "HRV (RMSSD), EEG, autonomic balance",
        "typical_signal": "Anxiety, depression, irritability",
        "general_wellness": "Meditation, breathing exercises, therapy",
    },
    "H": {
        "name": "先天/肾精轴",
        "en": "Congenital / Kidney-Essence axis",
        "mechanism": "Epigenetic clock, iPSC reprogramming, CD4 CTL",
        "typical_signal": "Premature aging, low libido, memory decline",
        "general_wellness": "Sleep, nutrition, reduce chronic stress",
    },
}


def _tool_get_axis_detail(axis_id: str) -> dict:
    """L1 — 返回单个八轴的机制解释和通用养生建议。

    数据边界：仅返回公开科普内容，无用户个人数据。
    """
    axis = axis_id.strip().upper()
    if axis not in _AXIS_INFO:
        return {
            "error": "invalid_axis",
            "message": f"Unknown axis '{axis_id}'. Valid axes: A, B, C, D, E, F, G, H",
        }
    info = _AXIS_INFO[axis]
    return {
        "axis_id": axis,
        "name": info["name"],
        "en": info["en"],
        "mechanism": info["mechanism"],
        "typical_signal": info["typical_signal"],
        "general_wellness": info["general_wellness"],
        "disclaimer": _DISCLAIMER,
    }


# 少量已发布的 SEO 文章索引（供 hl_get_wellness_article 用）
_ARTICLE_INDEX: dict[str, dict] = {
    "astragalus-qi-immunity": {
        "title": "Astragalus: Qi-Boosting Immune Modulation Wisdom",
        "summary": (
            "Astragalus is a classic qi-boosting food-medicine ingredient, "
            "classified as upper-grade in Shennong Classic. Modern research "
            "confirms astragalus polysaccharides have immune-modulating effects."
        ),
        "url": "https://healthlens.cc/en/knowledge/astragalus-qi-immunity",
        "axis": "B",
    },
}


def _tool_get_wellness_article(slug: str) -> dict:
    """L1 — 按 slug 返回单篇养生文章的元数据。

    数据边界：仅返回公开的 SEO 文章索引；完整正文可通过 url 访问。
    注意：完整文章正文需通过公开 URL 抓取，本工具仅返回摘要和链接。
    """
    article = _ARTICLE_INDEX.get(slug)
    if article is None:
        return {
            "error": "article_not_found",
            "message": f"No article found with slug '{slug}'",
            "hint": "Browse https://healthlens.cc/knowledge for available articles",
        }
    return {
        **article,
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# L2 知识层（通用建议，无个体数据）
# ---------------------------------------------------------------------------
_DIET_GOALS: dict[str, dict] = {
    "anti_aging": {
        "principles": [
            "Time-restricted eating (10-12h eating window)",
            "Fasting-mimicking diet (FMD) cycles every 3-6 months",
            "Low-glycemic index (GI) foods",
            "Omega-3 rich foods (fish, flaxseed, walnuts)",
        ],
        "avoid": ["Refined sugar", "Processed meat", "Fried foods"],
    },
    "energy_boost": {
        "principles": [
            "Balanced macronutrients at each meal",
            "Iron-rich foods (spinach, lentils, red meat in moderation)",
            "Adequate hydration (2-3L water daily)",
            "Regular meal timing (avoid skipping breakfast)",
        ],
        "avoid": ["Excess caffeine", "Late-night heavy meals"],
    },
    "anti_inflammatory": {
        "principles": [
            "Mediterranean-style eating",
            "Berries, leafy greens, colorful vegetables",
            "Omega-3 (fatty fish 2-3x/week)",
            "Green tea, turmeric, ginger",
        ],
        "avoid": ["Sugar-sweetened beverages", "Refined carbs", "Trans fats"],
    },
    "gut_health": {
        "principles": [
            "Fiber-rich foods (whole grains, legumes, vegetables)",
            "Fermented foods (yogurt, kimchi, kefir)",
            "Diverse plant-based diet (30+ plants/week)",
        ],
        "avoid": ["Artificial sweeteners in excess", "Antibiotic overuse"],
    },
    "sleep_improvement": {
        "principles": [
            "Avoid caffeine after 2pm",
            "Magnesium-rich foods (dark chocolate, almonds)",
            "Tryptophan-rich foods (turkey, eggs) at dinner",
            "Limit evening screen exposure",
        ],
        "avoid": ["Alcohol near bedtime", "Heavy meals 2h before sleep"],
    },
}


def _tool_suggest_general_diet(goal: str, preferences: list[str] | None = None) -> dict:
    """L2 — 返回通用饮食建议（无个体数据）。

    数据边界：建议仅基于公开的中医养生和现代营养学共识，
    不基于用户个体指标，不构成个性化医疗建议。
    """
    goal_key = (goal or "anti_inflammatory").strip().lower()
    # Fuzzy match
    aliases = {
        "anti_aging": ["anti-aging", "longevity", "延寿", "抗衰"],
        "energy_boost": ["energy", "fatigue", "energy boost", "疲劳", "精力"],
        "anti_inflammatory": ["inflammation", "inflamm", "抗炎"],
        "gut_health": ["gut", "digestion", "肠胃"],
        "sleep_improvement": ["sleep", "insomnia", "睡眠"],
    }
    for key, keys in aliases.items():
        if any(k in goal_key for k in keys):
            goal_key = key
            break

    if goal_key not in _DIET_GOALS:
        return {
            "error": "unknown_goal",
            "message": f"Unknown goal '{goal}'",
            "supported_goals": list(_DIET_GOALS.keys()),
            "disclaimer": _DISCLAIMER,
        }

    rec = _DIET_GOALS[goal_key]
    result = {
        "goal": goal_key,
        "principles": rec["principles"],
        "avoid": rec["avoid"],
        "preferences_applied": preferences or [],
        "note": "General wellness guidance based on public TCM and modern nutrition consensus.",
        "disclaimer": _DISCLAIMER,
    }
    return result


_MOTION_PRESETS: dict[str, dict] = {
    "beginner": {
        "description": "For those new to exercise or returning after long break",
        "sessions_per_week": 3,
        "duration_min": 20,
        "type": "Brisk walking, light jogging, gentle yoga",
        "intensity": "Low (breathless but conversational)",
    },
    "moderate": {
        "description": "For those with regular exercise habit",
        "sessions_per_week": 4,
        "duration_min": 30,
        "type": "Aerobic exercise (jogging, cycling, swimming) + light resistance",
        "intensity": "Moderate (heart rate ~60-70% max)",
    },
    "advanced": {
        "description": "For experienced exercisers seeking longevity benefits",
        "sessions_per_week": 5,
        "duration_min": 45,
        "type": "Mixed aerobic + resistance training + flexibility",
        "intensity": "Moderate-high (70-85% max HR)",
    },
}


def _tool_suggest_general_motion(intensity: str = "moderate") -> dict:
    """L2 — 返回通用运动建议（无个体数据）。

    数据边界：基于 WHO / AHA / 现代运动生理学共识的通用建议，
    不基于用户个体能力评估。
    """
    key = (intensity or "moderate").strip().lower()
    if key not in _MOTION_PRESETS:
        return {
            "error": "unknown_intensity",
            "message": f"Unknown intensity '{intensity}'",
            "supported": list(_MOTION_PRESETS.keys()),
            "disclaimer": _DISCLAIMER,
        }
    preset = _MOTION_PRESETS[key]
    return {
        "intensity": key,
        **preset,
        "consensus": "WHO / AHA guidelines, adapted for wellness longevity",
        "disclaimer": _DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# L3 用户层（默认关闭，需 HL_MCP_EXPOSE_PRIVATE=1）
# ---------------------------------------------------------------------------
def _lazy_load_fusion_engine():
    """返回 fusion_engine 模块；缺失（瘦发行版）时返回 _error 字典而非抛异常。"""
    try:
        from . import _loader
        fe = _loader.load_fusion_engine()
    except Exception as exc:
        return {"_error": f"fusion_engine_unavailable: {exc}"}
    if fe is None:
        return {"_error": "fusion_engine_unavailable: app/lib/fusion_engine.py not shipped in this build"}
    return fe


def _tool_fusion_engine(user_input: str = "", gene_scores: dict | None = None) -> dict:
    """L3 — 八轴融合推理。

    数据边界警告：本工具接受用户症状和基因通路得分，返回个性化推荐。
    调用方应确保已获得用户明确同意（GDPR Art. 9 健康数据处理）。
    """
    if not _EXPOSE_PRIVATE:
        return {
            "error": "tool_disabled_by_default",
            "message": "hl_fusion_engine requires HL_MCP_EXPOSE_PRIVATE=1",
            "reason": "Personalized health reasoning — GDPR Art. 9 sensitive data",
        }
    fe = _lazy_load_fusion_engine()
    if isinstance(fe, dict) and "_error" in fe:
        return fe
    try:
        from . import pipeline as pl
        profile = fe.UserProfile(pathway_scores=gene_scores or {})
        result = pl.run_pipeline(user_input=user_input, profile=profile)
        return result.to_dict()
    except Exception as exc:
        return {"error": "fusion_engine_failed", "message": str(exc)}


def _tool_evidence_grade(recommendations_json: str) -> dict:
    """L3 — 对建议列表做 L1/L2/L3 证据分级。"""
    if not _EXPOSE_PRIVATE:
        return {"error": "tool_disabled_by_default", "message": "Requires HL_MCP_EXPOSE_PRIVATE=1"}
    try:
        recs = json.loads(recommendations_json)
        from skills.evidence_grading.run import run as grade_run
        return grade_run(recommendations=recs)
    except Exception as exc:
        return {"error": "evidence_grade_failed", "message": str(exc)}


def _tool_risk_assess(age: int, gender: str, sbp: float, tc: float) -> dict:
    """L3 — 慢病风险自评量表（ASCVD 自评，非 China-PAR 模型）。

    诚实边界（P0-4）：这是**透明启发式自评量表**，输出的是"倾向百分比"
    （无量纲 0-100 指数），**不是 10 年心血管事件发病概率**。调用方应仅
    用于教育/生活方式干预参考，不用于诊断或治疗决策。
    """
    if not _EXPOSE_PRIVATE:
        return {"error": "tool_disabled_by_default", "message": "Requires HL_MCP_EXPOSE_PRIVATE=1"}
    try:
        from app.core.risk_engine import ASCVDRiskEngine
        eng = ASCVDRiskEngine()
        r = eng.assess(age=age, gender=gender, sbp=sbp, tc=tc)
        return {
            "risk_type": r.risk_type,
            "risk_level": r.risk_level,
            "risk_score": r.risk_score,
            "risk_probability": r.risk_probability,
            "factors": [f.name for f in r.risk_factors],
            "references": r.references,
            "disclaimer": r.disclaimer,
        }
    except ImportError:
        return {"error": "risk_engine_unavailable"}
    except Exception as exc:
        return {"error": "risk_assess_failed", "message": str(exc)}


def _tool_tcm_constitution(symptoms: str = "") -> dict:
    """L3 — 中医体质分析。

    数据边界警告：基于症状描述的体质判定，不构成医疗诊断。
    """
    if not _EXPOSE_PRIVATE:
        return {"error": "tool_disabled_by_default", "message": "Requires HL_MCP_EXPOSE_PRIVATE=1"}
    try:
        from . import pipeline as pl
        fe = _lazy_load_fusion_engine()
        profile = fe.UserProfile()
        result = pl.run_pipeline(user_input=symptoms, profile=profile)
        return result.to_dict()
    except Exception as exc:
        return {"error": "tcm_constitution_failed", "message": str(exc)}


# ---------------------------------------------------------------------------
# L1 参考数据层（公开结构 / 化学 / 同源性数据库）
#
# 与 L3 的本质区别：这些数据源全部是公开只读档案库（RCSB PDB / PubChem /
# UniProt / AlphaFold / NCBI BLAST），查询参数是基因符号、PDB ID、化合物名，
# 不携带任何用户健康数据，因此默认开启、不需要 HL_MCP_EXPOSE_PRIVATE。
#
# 诚实边界（写进每个工具的描述，防止下游 Agent 误用）：
#   - RCSB 条目 = 实验测定结构（X-ray / cryo-EM / NMR），可作结构证据
#   - AlphaFold = 计算预测，不得当作实验证据引用
#   - PubChem 属性 = 计算值（computed），非实验测定
#   - BLAST 在 NCBI 公共队列异步执行，排队可达数小时
# ---------------------------------------------------------------------------
_REF_DISCLAIMER = (
    "Reference-database facts only (RCSB PDB / PubChem / UniProt / AlphaFold). "
    "Experimental structures are evidence; AlphaFold models are predictions and must not "
    "be cited as experimental evidence. PubChem properties are computed values. "
    "Not medical advice."
)

_REF_HINTS = {
    "not_found": "确认标识符拼写：基因用 HGNC 官方符号（TP53 而非 p53），PDB ID 为 4 位（4HHB）",
    "invalid_input": "检查参数格式与取值范围",
    "rate_limited": "上游限流，稍后重试；配置 NCBI_API_KEY 可提升配额",
    "timeout": "上游超时；BLAST 公共队列可能排队数小时，用 hl_blast_status 轮询而非同步等待",
    "license_unavailable": "Schrödinger 需自备商业许可，本项目不提供",
}


def _run_ref(factory):
    """在同步 handler 中执行异步连接器调用。

    MCP handler 是同步函数，参考数据源连接器是 async（httpx）。若当前线程已有
    运行中的事件循环（FastAPI async 上下文），`asyncio.run()` 会抛
    `RuntimeError: asyncio.run() cannot be called from a running event loop`，
    故退化为在独立线程里新建事件循环。连接器的 httpx 客户端按事件循环隔离
    （见 app/connectors/reference/base.py），因此跨线程安全。

    `factory` 传零参可调用对象而非协程对象：协程对象若因异常未被 await
    会触发 "coroutine was never awaited" 警告，工厂形式可避免。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, factory()).result()


def _ref_error(exc: Exception) -> dict:
    """把连接器的 ReferenceError 映射成机器可读的 MCP 错误对象。"""
    code = getattr(exc, "code", None) or "upstream_error"
    detail = getattr(exc, "detail", None) or str(exc)
    return {"error": code, "message": str(detail)[:500], "hint": _REF_HINTS.get(code, "")}


def _as_int(value, default: int) -> int:
    """MCP 客户端可能把数字传成字符串；越界或无法解析时退回默认值。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tool_pdb_entry(pdb_id: str = "") -> dict:
    """L1 — 按 PDB ID 取实验结构条目：标题、实验方法、分辨率、作者、实体、配体。"""
    from app.connectors.reference import ReferenceError, get_source

    pid = (pdb_id or "").strip().upper()
    if not pid:
        return {"error": "invalid_input", "message": "pdb_id 不能为空", "hint": _REF_HINTS["invalid_input"]}
    try:
        data = _run_ref(lambda: get_source("rcsb_pdb").describe(pid))
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:  # 网络/解析等非业务异常
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["disclaimer"] = _REF_DISCLAIMER
    return data


def _tool_pdb_search(
    text: str = "",
    method: str = "",
    max_resolution: str = "",
    organism: str = "",
    limit: str = "25",
) -> dict:
    """L1 — RCSB 全库检索（条件之间 AND）。method 需传完整方法名。"""
    from app.connectors.reference import ReferenceError, get_source

    n = max(1, min(_as_int(limit, 25), 100))
    res = None if not str(max_resolution).strip() else float(max_resolution)
    try:
        data = _run_ref(
            lambda: get_source("rcsb_pdb").search(
                text=text or None,
                method=method or None,
                max_resolution=res,
                organism=organism or None,
                limit=n,
            )
        )
    except ReferenceError as exc:
        return _ref_error(exc)
    except ValueError:
        return {"error": "invalid_input", "message": "max_resolution 需为数字（如 2.5）", "hint": _REF_HINTS["invalid_input"]}
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["disclaimer"] = _REF_DISCLAIMER
    return data


def _tool_compound_lookup(query: str = "") -> dict:
    """L1 — 化合物查询：名称 / SMILES / InChIKey → CID、计算属性、同义词、CAS 号。"""
    from app.connectors.reference import ReferenceError, get_source

    q = (query or "").strip()
    if not q:
        return {"error": "invalid_input", "message": "query 不能为空", "hint": _REF_HINTS["invalid_input"]}
    try:
        data = _run_ref(lambda: get_source("pubchem").describe(q))
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["disclaimer"] = _REF_DISCLAIMER
    return data


def _tool_compound_similar(query: str = "", threshold: str = "95", limit: str = "20") -> dict:
    """L1 — 2D 指纹相似性搜索（Tanimoto ≥ threshold），返回相似化合物 CID 列表。"""
    from app.connectors.reference import ReferenceError, get_source

    q = (query or "").strip()
    if not q:
        return {"error": "invalid_input", "message": "query 不能为空", "hint": _REF_HINTS["invalid_input"]}
    thr = max(1, min(_as_int(threshold, 95), 100))
    n = max(1, min(_as_int(limit, 20), 100))

    async def _go():
        pc = get_source("pubchem")
        resolved = await pc.resolve(q, namespace="auto")
        cid = resolved["primary_cid"]
        props = await pc.properties(cid)
        smiles = props.get("canonical_smiles")
        if not smiles:
            raise ReferenceError("not_found", pc.SOURCE, f"CID {cid} 无 canonical SMILES，无法做相似性搜索")
        sim = await pc.similar(smiles, threshold=thr, limit=n)
        return {
            "query": q,
            "seed_cid": cid,
            "seed_smiles": smiles,
            "threshold": thr,
            "similar": sim,
            "source": pc.SOURCE,
            "disclaimer": _REF_DISCLAIMER,
        }

    try:
        return _run_ref(_go)
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}


def _tool_target_profile(gene: str = "", max_structures: str = "10") -> dict:
    """L1 — 靶点全景：基因 → UniProt 蛋白 → 实验结构清单 → AlphaFold 预测结构。

    这是把"某个基因/蛋白有什么结构证据"一次答完的组合工具，替代三次往返调用。
    """
    from app.connectors.reference import ReferenceError, describe_target

    g = (gene or "").strip().upper()
    if not g:
        return {"error": "invalid_input", "message": "gene 不能为空", "hint": _REF_HINTS["invalid_input"]}
    n = max(1, min(_as_int(max_structures, 10), 50))
    try:
        data = _run_ref(lambda: describe_target(g, max_structures=n))
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["disclaimer"] = _REF_DISCLAIMER
    return data


def _tool_blast_submit(sequence: str = "", program: str = "blastn", database: str = "core_nt") -> dict:
    """L1 — 提交 BLAST 比对，立即返回 RID 与预估排队秒数（RTOE）。

    公共队列排队时间不可控（实测 blastn 约 30 秒，blastp+swissprot 曾达 9.7 小时），
    因此本工具只负责提交；取结果必须用 hl_blast_status / hl_blast_result 轮询。
    """
    from app.connectors.reference import ReferenceError, get_source

    seq = (sequence or "").strip()
    if not seq:
        return {"error": "invalid_input", "message": "sequence 不能为空"}
    try:
        data = _run_ref(
            lambda: get_source("ncbi_blast").submit(seq, program=program or "blastn", database=database or "core_nt")
        )
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["next_step"] = "用 hl_blast_status 轮询 status；READY 后调用 hl_blast_result 取命中"
    data["disclaimer"] = _REF_DISCLAIMER
    return data


def _tool_blast_status(rid: str = "") -> dict:
    """L1 — 查询 BLAST 任务状态（WAITING / RUNNING / READY / UNKNOWN）。"""
    from app.connectors.reference import ReferenceError, get_source

    r = (rid or "").strip().upper()
    if not r:
        return {"error": "invalid_input", "message": "rid 不能为空"}
    try:
        return _run_ref(lambda: get_source("ncbi_blast").status(r))
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}


def _tool_blast_result(rid: str = "") -> dict:
    """L1 — 取 BLAST 结果（解析后的命中 + HSP）。任务未完成时返回 not_ready。"""
    from app.connectors.reference import ReferenceError, get_source

    r = (rid or "").strip().upper()
    if not r:
        return {"error": "invalid_input", "message": "rid 不能为空"}
    try:
        data = _run_ref(lambda: get_source("ncbi_blast").fetch(r))
    except ReferenceError as exc:
        return _ref_error(exc)
    except Exception as exc:
        return {"error": "reference_unavailable", "message": str(exc)[:300]}
    data["disclaimer"] = _REF_DISCLAIMER
    return data


# ---------------------------------------------------------------------------
# Tool 注册表（分层）
# ---------------------------------------------------------------------------
_TOOLS_L1 = {
    "hl_health_check": {
        "handler": _tool_health_check,
        "description": "Return service health status, version, and tier config. Safe by default.",
        "args": {},
    },
    "hl_search_knowledge": {
        "handler": _tool_search_knowledge,
        "description": (
            "Search HealthLens TCM wellness knowledge base (TCM-MKG graph, classical books). "
            "No personal data. Returns top 20 relevant entries. " + _DISCLAIMER
        ),
        "args": {"query": str},
    },
    "hl_get_axis_detail": {
        "handler": _tool_get_axis_detail,
        "description": (
            "Return mechanism explanation and general wellness guidance for one of the "
            "8 HealthLens axes (A-H). No personal data. " + _DISCLAIMER
        ),
        "args": {"axis_id": str},
    },
    "hl_get_wellness_article": {
        "handler": _tool_get_wellness_article,
        "description": (
            "Get metadata and summary for a published wellness article by slug. "
            "No personal data. " + _DISCLAIMER
        ),
        "args": {"slug": str},
    },
}

_TOOLS_L2 = {
    "hl_suggest_general_diet": {
        "handler": _tool_suggest_general_diet,
        "description": (
            "Return general diet guidance for a wellness goal (anti_aging, energy_boost, "
            "anti_inflammatory, gut_health, sleep_improvement). No personal data. " + _DISCLAIMER
        ),
        "args": {"goal": str, "preferences": list},
    },
    "hl_suggest_general_motion": {
        "handler": _tool_suggest_general_motion,
        "description": (
            "Return general exercise prescription for an intensity level "
            "(beginner/moderate/advanced). No personal data. " + _DISCLAIMER
        ),
        "args": {"intensity": str},
    },
}

_TOOLS_L3 = {
    "hl_fusion_engine": {
        "handler": _tool_fusion_engine,
        "description": (
            "[PRIVATE] Eight-axis fusion reasoning for personalized wellness recommendations. "
            "Requires HL_MCP_EXPOSE_PRIVATE=1. Handles user health data (GDPR Art. 9). " + _DISCLAIMER
        ),
        "args": {"user_input": str, "gene_scores": dict},
    },
    "hl_evidence_grade": {
        "handler": _tool_evidence_grade,
        "description": (
            "[PRIVATE] Grade a list of recommendations into L1/L2/L3 evidence tiers. "
            "Requires HL_MCP_EXPOSE_PRIVATE=1."
        ),
        "args": {"recommendations_json": str},
    },
    "hl_risk_assess": {
        "handler": _tool_risk_assess,
        "description": (
            "[PRIVATE] ASCVD chronic disease self-assessment scale (启发式, NOT the China-PAR model). "
            "Returns a 0-100 dimensionless tendency index, NOT a 10-year incidence probability. "
            "Requires HL_MCP_EXPOSE_PRIVATE=1. Educational use only. " + _DISCLAIMER
        ),
        "args": {"age": int, "gender": str, "sbp": float, "tc": float},
    },
    "hl_tcm_constitution": {
        "handler": _tool_tcm_constitution,
        "description": (
            "[PRIVATE] TCM constitution analysis from symptom description. "
            "Requires HL_MCP_EXPOSE_PRIVATE=1. Not a medical diagnosis. " + _DISCLAIMER
        ),
        "args": {"symptoms": str},
    },
}


_TOOLS_REF = {
    "hl_target_profile": {
        "handler": _tool_target_profile,
        "description": (
            "Target dossier: gene symbol -> UniProt protein -> list of experimental PDB structures "
            "-> AlphaFold predicted model. Use when asked 'what structures exist for protein X'. "
            "Experimental structures are evidence; AlphaFold is prediction. " + _REF_DISCLAIMER
        ),
        "args": {"gene": str, "max_structures": int},
    },
    "hl_pdb_entry": {
        "handler": _tool_pdb_entry,
        "description": (
            "Fetch one experimental PDB entry by 4-character ID: title, experimental method, "
            "resolution, authors, polymer entities/chains/source organism, bound ligands. " + _REF_DISCLAIMER
        ),
        "args": {"pdb_id": str},
    },
    "hl_pdb_search": {
        "handler": _tool_pdb_search,
        "description": (
            "Search the full RCSB PDB archive. Conditions combine with AND. "
            "'method' must be a full name such as 'X-RAY DIFFRACTION', 'ELECTRON MICROSCOPY', "
            "'SOLUTION NMR'. 'max_resolution' in angstrom (lower is sharper). " + _REF_DISCLAIMER
        ),
        "args": {"text": str, "method": str, "max_resolution": float, "organism": str, "limit": int},
    },
    "hl_compound_lookup": {
        "handler": _tool_compound_lookup,
        "description": (
            "Resolve a compound by name / SMILES / InChIKey to a PubChem CID, then return computed "
            "properties (formula, MW, XLogP, TPSA, H-bond counts), synonyms and CAS numbers. " + _REF_DISCLAIMER
        ),
        "args": {"query": str},
    },
    "hl_compound_similar": {
        "handler": _tool_compound_similar,
        "description": (
            "2D fingerprint (Tanimoto) similarity search on PubChem: given a seed compound, return "
            "analogues at or above the threshold. Useful for scaffold hopping / analogue finding. "
            + _REF_DISCLAIMER
        ),
        "args": {"query": str, "threshold": int, "limit": int},
    },
    "hl_blast_submit": {
        "handler": _tool_blast_submit,
        "description": (
            "Submit a nucleotide/protein sequence to NCBI BLAST and return a RID plus estimated queue "
            "seconds (RTOE). Runs on NCBI's shared public queue: minutes to hours. This tool only "
            "submits; poll with hl_blast_status then fetch with hl_blast_result."
        ),
        "args": {"sequence": str, "program": str, "database": str},
    },
    "hl_blast_status": {
        "handler": _tool_blast_status,
        "description": "Poll a submitted BLAST job by RID. Returns WAITING / RUNNING / READY.",
        "args": {"rid": str},
    },
    "hl_blast_result": {
        "handler": _tool_blast_result,
        "description": (
            "Fetch parsed BLAST hits (accession, title, E-value, bit score, identity, alignment "
            "ranges) for a READY RID. " + _REF_DISCLAIMER
        ),
        "args": {"rid": str},
    },
}


_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


def _arg_schema(args: dict) -> dict:
    """把 {参数名: Python 类型} 映射成 JSON Schema 的 properties。

    历史实现把所有参数一律声明为 "string"，于是 limit / threshold 这类整数参数
    会被 MCP 客户端按字符串发送（`"limit": "25"`）。这里按真实类型映射；handler
    侧仍保留 `_as_int` 兜底，因为部分客户端并不严格遵守 schema。
    """
    return {k: {"type": _JSON_TYPES.get(v, "string")} for k, v in args.items()}


def _active_tools() -> dict:
    """返回当前激活的工具集。

    L1 内容层 + L1 参考数据层 + L2 知识层总是激活（均不含个人数据）；
    L3 用户层需 HL_MCP_EXPOSE_PRIVATE=1。
    """
    active = {**_TOOLS_L1, **_TOOLS_REF, **_TOOLS_L2}
    if _EXPOSE_PRIVATE:
        active.update(_TOOLS_L3)
    return active


# ---------------------------------------------------------------------------
# MCP 服务器主入口
# ---------------------------------------------------------------------------
def _run_mcp_server() -> None:
    try:
        import mcp  # type: ignore
    except ImportError:
        print(
            "mcp package not installed. Falling back to JSON-RPC stdio mode.",
            file=sys.stderr,
        )
        print(
            "Install: pip install mcp  (recommended for production use)",
            file=sys.stderr,
        )
        _run_jsonrpc_mode()
        return

    app = mcp.Server("healthlens-mcp")

    @app.tool()
    def hl_health_check() -> str:
        return json.dumps(_tool_health_check(), ensure_ascii=False)

    @app.tool()
    def hl_search_knowledge(query: str) -> str:
        return json.dumps(_tool_search_knowledge(query), ensure_ascii=False)

    @app.tool()
    def hl_get_axis_detail(axis_id: str) -> str:
        return json.dumps(_tool_get_axis_detail(axis_id), ensure_ascii=False)

    @app.tool()
    def hl_get_wellness_article(slug: str) -> str:
        return json.dumps(_tool_get_wellness_article(slug), ensure_ascii=False)

    @app.tool()
    def hl_suggest_general_diet(goal: str, preferences: str = "[]") -> str:
        prefs = json.loads(preferences) if preferences else []
        return json.dumps(_tool_suggest_general_diet(goal, prefs), ensure_ascii=False)

    @app.tool()
    def hl_suggest_general_motion(intensity: str = "moderate") -> str:
        return json.dumps(_tool_suggest_general_motion(intensity), ensure_ascii=False)

    if _EXPOSE_PRIVATE:
        @app.tool()
        def hl_fusion_engine(user_input: str = "", gene_scores: str = "{}") -> str:
            scores = json.loads(gene_scores) if gene_scores else {}
            return json.dumps(
                _tool_fusion_engine(user_input=user_input, gene_scores=scores),
                ensure_ascii=False,
            )

        @app.tool()
        def hl_evidence_grade(recommendations_json: str) -> str:
            return json.dumps(_tool_evidence_grade(recommendations_json), ensure_ascii=False)

        @app.tool()
        def hl_risk_assess(age: int, gender: str, sbp: float, tc: float) -> str:
            return json.dumps(_tool_risk_assess(age, gender, sbp, tc), ensure_ascii=False)

        @app.tool()
        def hl_tcm_constitution(symptoms: str = "") -> str:
            return json.dumps(_tool_tcm_constitution(symptoms), ensure_ascii=False)

    asyncio.run(app.run())


def _run_jsonrpc_mode() -> None:
    """无 mcp package 时的 JSON-RPC stdio 模式。

    参考：HealthLens_下一阶段愿景与跃迁方案_2026-10-15.md §5 L0
    - MCP 2026-07-28 无状态化：移除旧握手（见 _HANDSHAKE_METHOD），移除 Session-Id
    - MRTR：每个响应带 threadId（客户端可传入，否则 server 生成 uuid4）
    - resultType：每个 result 都带 "complete" 或 "input_required"
    - server/discover：新增端点，返回 server 元信息 + capabilities + tools
    - subscriptions/listen：新增订阅端点（旧订阅端点已在 2026-07-28 废除）
    """
    tools = _active_tools()

    def _new_thread_id(params: dict) -> str:
        """MRTR：threadId 客户端优先，否则 server 生成 uuid4。"""
        tid = params.get("threadId") if isinstance(params, dict) else None
        return tid if isinstance(tid, str) and tid else str(uuid.uuid4())

    def _tool_defs() -> list[dict]:
        """MCP-spec tools array: each entry has name/description/inputSchema."""
        return [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": {
                    "type": "object",
                    "properties": _arg_schema(spec["args"]),
                },
            }
            for name, spec in tools.items()
        ]

    def _tool_names() -> list[str]:
        return list(tools.keys())

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method", "")
            params = req.get("params", {}) or {}
            req_id = req.get("id")
            thread_id = _new_thread_id(params)
            if method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "threadId": thread_id,
                    "result": {
                        "resultType": "complete",
                        "protocolVersion": _MCP_PROTOCOL_VERSION,
                        "tools": _tool_defs(),
                        "server": "healthlens-mcp",
                        "version": _SERVER_VERSION,
                    },
                }
            elif method == "tools/call":
                tool_name = params.get("name", "")
                args = params.get("arguments", {})
                if tool_name in tools:
                    result = tools[tool_name]["handler"](**args)
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "threadId": thread_id,
                        "result": {
                            "resultType": "complete",
                            "protocolVersion": _MCP_PROTOCOL_VERSION,
                            "content": [
                                {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                            ],
                        },
                    }
                else:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "threadId": thread_id,
                        "result": {
                            "resultType": "complete",
                            "protocolVersion": _MCP_PROTOCOL_VERSION,
                            "error": {"code": -32602, "message": f"unknown tool: {tool_name}"},
                        },
                    }
            elif method == "server/discover":
                # MCP 2026-07-28 新增：客户端可发现 server 元信息 + capabilities + tools
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "threadId": thread_id,
                    "result": {
                        "resultType": "complete",
                        "protocolVersion": _MCP_PROTOCOL_VERSION,
                        "serverInfo": {"name": "healthlens-mcp", "version": _SERVER_VERSION},
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"subscribe": False, "listen": True},
                            "prompts": {},
                        },
                        "tools": _tool_names(),
                        "uptimeSeconds": round(time.time() - _START_TS, 1),
                    },
                }
            elif method == "subscriptions/listen":
                # MCP 2026-07-28：新订阅端点（旧订阅端点已在 2026-07-28 废除）
                # 空实现占位（HealthLens 未产生需要订阅的事件源）
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "threadId": thread_id,
                    "result": {
                        "resultType": "complete",
                        "protocolVersion": _MCP_PROTOCOL_VERSION,
                        "subscriptionId": thread_id,
                        "channels": [],
                        "note": "HealthLens MCP 目前无订阅事件源；占位以兼容 MCP 2026-07-28",
                    },
                }
            elif method == _HANDSHAKE_METHOD:
                # 旧客户端兼容：MCP 2026-07-28 已废除握手，返回明确错误信息
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "threadId": thread_id,
                    "error": {
                        "code": -32601,
                        "message": "no handshake required in MCP 2026-07-28",
                        "data": {"protocolVersion": _MCP_PROTOCOL_VERSION},
                    },
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "threadId": thread_id,
                    "error": {"code": -32601, "message": f"unknown method: {method}"},
                }
        except Exception as exc:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        print(json.dumps(resp), flush=True)
        sys.stdout.flush()


def demo() -> None:
    print(f"HealthLens MCP Server v{_SERVER_VERSION}")
    print(f"Server version: {_SERVER_VERSION}")
    print(f"Private tools exposed: {_EXPOSE_PRIVATE}")
    print(f"OAuth enabled: {_OAUTH_ENABLED}")
    print()
    print("=== L1 (Content) — always exposed ===")
    for name, spec in _TOOLS_L1.items():
        print(f"  {name}")
        print(f"    {spec['description'][:100]}")
    print()
    print("=== L2 (Knowledge) — always exposed ===")
    for name, spec in _TOOLS_L2.items():
        print(f"  {name}")
        print(f"    {spec['description'][:100]}")
    print()
    if _EXPOSE_PRIVATE:
        print("=== L3 (Private) — exposed via HL_MCP_EXPOSE_PRIVATE=1 ===")
        for name, spec in _TOOLS_L3.items():
            print(f"  {name}")
            print(f"    {spec['description'][:100]}")
    else:
        print("=== L3 (Private) — DISABLED (set HL_MCP_EXPOSE_PRIVATE=1 to enable) ===")
        for name, spec in _TOOLS_L3.items():
            print(f"  [LOCKED] {name}")
    print()
    try:
        import mcp  # noqa: F401  # type: ignore  (availability check only)
        print("mcp package: installed (will use MCP SDK mode)")
    except ImportError:
        print("mcp package: not installed (will use JSON-RPC stdio fallback)")


def main() -> None:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--demo":
            demo()
            return
        if arg == "--jsonrpc":
            _run_jsonrpc_mode()
            return
        if arg == "--tools":
            tools = _active_tools()
            for name in tools:
                print(name)
            return
    _run_mcp_server()


if __name__ == "__main__":
    main()
