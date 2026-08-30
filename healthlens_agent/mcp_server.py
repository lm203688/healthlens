"""
mcp_server.py — HealthLens MCP Server

暴露 HealthLens 核心能力为 MCP 工具，供外部 Agent/Copilot 调用。
支持的工具：
  - fusion_engine: 八轴融合推理
  - evidence_grade: 证据分级
  - risk_assess: 慢病风险评估
  - tcm_constitution: 中医体质分析
  - knowledge_search: 古籍知识库搜索

运行方式：
  python -m healthlens_agent mcp
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ._loader import load_fusion_engine  # noqa: E402

try:
    import mcp  # type: ignore  # noqa: E402
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------

_fe = load_fusion_engine()
_fe_recommend = _fe.recommend
_fe_user_profile = _fe.UserProfile


def _tool_fusion_engine(user_input: str = "", gene_scores: dict = None) -> dict:
    """HealthLens 八轴融合推理：输入症状描述+基因通路得分，输出个性化建议。"""
    from . import pipeline as pl
    profile = _fe_user_profile(pathway_scores=gene_scores or {})
    result = pl.run_pipeline(user_input=user_input, profile=profile)
    return result.to_dict()


def _tool_evidence_grade(recommendations_json: str) -> dict:
    """对建议列表做 L1/L2/L3 证据分级。"""
    recs = json.loads(recommendations_json)
    from skills.evidence_grading.run import run as grade_run
    return grade_run(recommendations=recs)


def _tool_risk_assess(age: int, gender: str, sbp: float, tc: float) -> dict:
    """慢病风险评估（ASCVD 简化模型）。"""
    try:
        from app.core.risk_engine import ASCVDRiskEngine
    except ImportError:
        return {"error": "risk_engine 不可用"}
    eng = ASCVDRiskEngine()
    r = eng.assess(age=age, gender=gender, sbp=sbp, tc=tc)
    return {
        "risk_level": r.risk_level,
        "risk_score": r.risk_score,
        "risk_probability": r.risk_probability,
        "factors": [f.name for f in r.risk_factors],
    }


def _tool_tcm_constitution(symptoms: str = "") -> dict:
    """中医体质分析：输入症状描述，输出体质类型+建议。"""
    from . import pipeline as pl
    profile = _fe_user_profile()
    result = pl.run_pipeline(user_input=symptoms, profile=profile)
    return result.to_dict()


def _tool_knowledge_search(query: str) -> dict:
    """中医古籍知识库搜索。"""
    from skills.tcm_text_mining.run import run as mining_run
    return mining_run(text=query)


# ---------------------------------------------------------------------------
# MCP 服务器主入口
# ---------------------------------------------------------------------------
def _run_mcp_server() -> None:
    if not _HAS_MCP:
        print("mcp package 未安装，使用 JSON-RPC 模拟模式", file=sys.stderr)
        print("安装：pip install mcp", file=sys.stderr)
        return _run_jsonrpc_mode()

    app = mcp.Server("healthlens-agent")

    @app.tool()
    def fusion_engine(user_input: str, gene_scores: str = "{}") -> str:
        scores = json.loads(gene_scores)
        result = _tool_fusion_engine(user_input=user_input, gene_scores=scores)
        return json.dumps(result, ensure_ascii=False)

    @app.tool()
    def evidence_grade(recommendations_json: str) -> str:
        result = _tool_evidence_grade(recommendations_json)
        return json.dumps(result, ensure_ascii=False)

    @app.tool()
    def risk_assess(age: int, gender: str, sbp: float, tc: float) -> str:
        result = _tool_risk_assess(age, gender, sbp, tc)
        return json.dumps(result, ensure_ascii=False)

    @app.tool()
    def tcm_constitution(symptoms: str) -> str:
        result = _tool_tcm_constitution(symptoms)
        return json.dumps(result, ensure_ascii=False)

    @app.tool()
    def knowledge_search(query: str) -> str:
        result = _tool_knowledge_search(query)
        return json.dumps(result, ensure_ascii=False)

    asyncio.run(app.run())


def _run_jsonrpc_mode() -> None:
    """无 mcp package 时的 JSON-RPC 模拟模式（stdio）。"""
    _tools: dict[str, callable] = {
        "fusion_engine": _tool_fusion_engine,
        "evidence_grade": _tool_evidence_grade,
        "risk_assess": _tool_risk_assess,
        "tcm_constitution": _tool_tcm_constitution,
        "knowledge_search": _tool_knowledge_search,
    }

    print(json.dumps({"jsonrpc": "2.0", "result": {"tools": list(_tools.keys())}}), flush=True)
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
                resp = {"jsonrpc": "2.0", "result": {"tools": list(_tools.keys())}}
            elif method in _tools:
                result = _tools[method](**params)
                resp = {"jsonrpc": "2.0", "result": result}
            else:
                resp = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "unknown method"}}
        except Exception as exc:
            resp = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}}
        print(json.dumps(resp), flush=True)
        sys.stdout.flush()


def demo():
    print("=== MCP Server 工具列表 ===")
    print("  fusion_engine:     八轴融合推理")
    print("  evidence_grade:    证据分级 L1/L2/L3")
    print("  risk_assess:       慢病风险评估")
    print("  tcm_constitution:  中医体质分析")
    print("  knowledge_search:  古籍知识库搜索")
    print(f"\n  mcp package: {'已安装' if _HAS_MCP else '未安装（使用 JSON-RPC 模式）'}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo()
    else:
        _run_mcp_server()
