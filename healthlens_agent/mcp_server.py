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
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SERVER_VERSION = "0.2.0"
_START_TS = time.time()

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
    try:
        from . import _loader
        return _loader.load_fusion_engine()
    except Exception as exc:
        return {"_error": f"fusion_engine_unavailable: {exc}"}


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
    """L3 — 慢病风险评估（ASCVD 简化模型）。

    数据边界警告：返回慢病风险等级，可能被视为医疗建议，
    调用方应仅用于教育/参考，不用于诊断。
    """
    if not _EXPOSE_PRIVATE:
        return {"error": "tool_disabled_by_default", "message": "Requires HL_MCP_EXPOSE_PRIVATE=1"}
    try:
        from app.core.risk_engine import ASCVDRiskEngine
        eng = ASCVDRiskEngine()
        r = eng.assess(age=age, gender=gender, sbp=sbp, tc=tc)
        return {
            "risk_level": r.risk_level,
            "risk_score": r.risk_score,
            "risk_probability": r.risk_probability,
            "factors": [f.name for f in r.risk_factors],
            "disclaimer": _DISCLAIMER,
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
            "[PRIVATE] ASCVD chronic disease risk assessment. Requires HL_MCP_EXPOSE_PRIVATE=1. "
            "Educational use only, not for diagnosis. " + _DISCLAIMER
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


def _active_tools() -> dict:
    """返回当前激活的工具集。L1+L2 总是激活；L3 需 HL_MCP_EXPOSE_PRIVATE=1。"""
    active = {**_TOOLS_L1, **_TOOLS_L2}
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
    """无 mcp package 时的 JSON-RPC stdio 模式。"""
    tools = _active_tools()

    # 首次响应工具清单
    print(
        json.dumps({
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": {
                            "type": "object",
                            "properties": {k: {"type": "string"} for k in spec["args"]},
                        },
                    }
                    for name, spec in tools.items()
                ],
                "server": "healthlens-mcp",
                "version": _SERVER_VERSION,
                "private_exposed": _EXPOSE_PRIVATE,
            },
        }),
        flush=True,
    )
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method", "")
            params = req.get("params", {})
            if method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "result": {
                        "tools": list(tools.keys()),
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
                        "id": req.get("id"),
                        "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
                    }
                else:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req.get("id"),
                        "error": {"code": -32602, "message": f"unknown tool: {tool_name}"},
                    }
            elif method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "healthlens-mcp", "version": _SERVER_VERSION},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "error": {"code": -32601, "message": f"unknown method: {method}"},
                }
        except Exception as exc:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(exc)}}
        print(json.dumps(resp), flush=True)
        sys.stdout.flush()


def demo() -> None:
    tools = _active_tools()
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
        import mcp  # type: ignore
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
