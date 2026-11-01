"""MCP 参考数据工具的契约测试（v0.39.0）。

背景：v0.38.0 把 RCSB / PubChem / UniProt / AlphaFold / BLAST 接成了 REST 层，
但 Agent 走的是 MCP，够不到这些能力——"有 API 没工具"和之前"有 API 没界面"
是同一类断层。本文件锁死三件事：

1. **默认可用**：参考数据全是公开只读库，不含个人数据，因此不需要
   HL_MCP_EXPOSE_PRIVATE，必须出现在默认工具集里。若哪天有人把它错划进 L3，
   这里会失败。
2. **参数类型正确**：历史实现把所有参数一律声明为 "string"，整数参数会被
   客户端按字符串发送。这里断言 schema 里 integer/number 与 Python 类型一致。
3. **诚实边界进描述**：AlphaFold 是预测不是实验证据、PubChem 属性是计算值、
   BLAST 走公共队列可能排队数小时——这些必须出现在工具描述里，否则下游
   Agent 会把预测当证据。

全部离线：不触网，用 monkeypatch 替掉连接器。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from healthlens_agent import mcp_server as m  # noqa: E402

REF_TOOLS = [
    "hl_target_profile",
    "hl_pdb_entry",
    "hl_pdb_search",
    "hl_compound_lookup",
    "hl_compound_similar",
    "hl_blast_submit",
    "hl_blast_status",
    "hl_blast_result",
]


class TestRegistration:
    def test_reference_tools_are_active_without_private_flag(self, monkeypatch):
        """参考数据工具不得依赖 HL_MCP_EXPOSE_PRIVATE。"""
        monkeypatch.setattr(m, "_EXPOSE_PRIVATE", False)
        active = m._active_tools()
        missing = [t for t in REF_TOOLS if t not in active]
        assert missing == [], f"参考数据工具未默认激活: {missing}"

    def test_l3_still_gated(self, monkeypatch):
        """加工具不能顺手把 L3 私有层也放出来。"""
        monkeypatch.setattr(m, "_EXPOSE_PRIVATE", False)
        active = m._active_tools()
        for name in ("hl_fusion_engine", "hl_risk_assess", "hl_tcm_constitution"):
            assert name not in active, f"L3 工具 {name} 在未开启私有层时泄漏"

    def test_every_reference_tool_has_handler_and_description(self):
        for name in REF_TOOLS:
            spec = m._TOOLS_REF[name]
            assert callable(spec["handler"]), f"{name} 缺少 handler"
            assert len(spec["description"]) > 40, f"{name} 描述过短，Agent 无法判断用途"
            assert isinstance(spec["args"], dict)


class TestHonestBoundaries:
    def test_predicted_structure_is_marked_as_prediction(self):
        """AlphaFold 必须在描述里被明确标为预测，不得与实验结构混同。"""
        desc = m._TOOLS_REF["hl_target_profile"]["description"].lower()
        assert "prediction" in desc or "predicted" in desc

    def test_compound_properties_marked_computed(self):
        desc = m._TOOLS_REF["hl_compound_lookup"]["description"].lower()
        assert "computed" in desc

    def test_blast_description_warns_about_queue(self):
        """BLAST 公共队列可达数小时，描述必须提示轮询而不是同步等待。"""
        desc = m._TOOLS_REF["hl_blast_submit"]["description"].lower()
        assert "queue" in desc and "poll" in desc


class TestArgSchema:
    def test_integer_args_are_not_declared_as_string(self):
        """回归：曾把所有参数声明为 string，导致 limit="25" 被原样传入。"""
        schema = m._arg_schema(m._TOOLS_REF["hl_target_profile"]["args"])
        assert schema["max_structures"]["type"] == "integer"
        assert schema["gene"]["type"] == "string"

    def test_float_arg_declared_as_number(self):
        schema = m._arg_schema(m._TOOLS_REF["hl_pdb_search"]["args"])
        assert schema["max_resolution"]["type"] == "number"
        assert schema["limit"]["type"] == "integer"

    @pytest.mark.parametrize(
        "raw,default,expected",
        [
            ("25", 10, 25),
            (25, 10, 25),
            ("", 10, 10),
            (None, 10, 10),
            ("abc", 10, 10),
        ],
    )
    def test_as_int_coerces_client_strings(self, raw, default, expected):
        assert m._as_int(raw, default) == expected


class TestRunRefBridge:
    def test_runs_when_no_loop_is_active(self):
        async def coro():
            return "ok"

        assert m._run_ref(coro) == "ok"

    @pytest.mark.asyncio
    async def test_runs_inside_a_running_loop(self):
        """MCP handler 可能在 FastAPI 的 async 上下文里被调用。

        此时 asyncio.run() 会抛 RuntimeError，_run_ref 必须退化到独立线程，
        否则工具在 Web 通道下必然 500。
        """

        async def coro():
            return "ok-in-loop"

        assert m._run_ref(coro) == "ok-in-loop"


class TestErrorSemantics:
    def test_empty_pdb_id_rejected_without_network(self):
        out = m._tool_pdb_entry(pdb_id="")
        assert out["error"] == "invalid_input"
        assert out["hint"]

    def test_short_pdb_id_rejected_without_network(self):
        """4 位校验必须在本地完成，不能把明显非法的 ID 打到上游。"""
        out = m._tool_pdb_entry(pdb_id="12")
        assert out["error"] == "invalid_input"

    def test_empty_compound_query_rejected(self):
        out = m._tool_compound_lookup(query="   ")
        assert out["error"] == "invalid_input"

    def test_empty_blast_sequence_rejected(self):
        out = m._tool_blast_submit(sequence="")
        assert out["error"] == "invalid_input"

    def test_reference_error_maps_to_machine_readable_code(self):
        from app.connectors.reference import ReferenceError

        out = m._ref_error(ReferenceError("not_found", "rcsb_pdb", "no such entry"))
        assert out["error"] == "not_found"
        assert "no such entry" in out["message"]
        assert out["hint"]


class TestHandlersWithStubbedSource:
    """用替身连接器验证 handler 的数据整形，不触网。"""

    def test_pdb_entry_handler_passes_through_and_adds_disclaimer(self, monkeypatch):
        class FakeRCSB:
            async def describe(self, pdb_id):
                return {"pdb_id": pdb_id, "title": "FAKE", "resolution_angstrom": 1.5}

        monkeypatch.setattr("app.connectors.reference.get_source", lambda name: FakeRCSB())
        out = m._tool_pdb_entry(pdb_id="4hhb")
        assert out["pdb_id"] == "4HHB", "PDB ID 应统一大写"
        assert out["title"] == "FAKE"
        assert "disclaimer" in out

    def test_compound_lookup_adds_disclaimer(self, monkeypatch):
        class FakePC:
            async def describe(self, q):
                return {"query": q, "compound": {"cid": 2244}}

        monkeypatch.setattr("app.connectors.reference.get_source", lambda name: FakePC())
        out = m._tool_compound_lookup(query="aspirin")
        assert out["compound"]["cid"] == 2244
        assert "disclaimer" in out

    def test_blast_submit_tells_caller_next_step(self, monkeypatch):
        class FakeBlast:
            async def submit(self, seq, **kw):
                return {"rid": "ABC123", "rtoe": 30}

        monkeypatch.setattr("app.connectors.reference.get_source", lambda name: FakeBlast())
        out = m._tool_blast_submit(sequence="MKWVTF", program="blastp", database="swissprot")
        assert out["rid"] == "ABC123"
        assert "hl_blast_status" in out["next_step"]

    def test_target_profile_clamps_max_structures(self, monkeypatch):
        seen = {}

        async def fake_describe_target(gene, *, max_structures=10, **kw):
            seen["gene"] = gene
            seen["max"] = max_structures
            return {"gene_symbol": gene}

        monkeypatch.setattr("app.connectors.reference.describe_target", fake_describe_target)
        m._tool_target_profile(gene="tp53", max_structures="9999")
        assert seen["gene"] == "TP53"
        assert seen["max"] == 50, "max_structures 应被夹到上限 50，避免一次拉爆上游"


def test_tool_defs_uses_typed_schema():
    """MCP tools/list 返回的 inputSchema 必须带真实类型。"""
    tools = m._active_tools()
    assert tools
    schema = m._arg_schema(tools["hl_pdb_search"]["args"])
    assert schema["max_resolution"]["type"] == "number"
    assert all("type" in v for v in schema.values())
