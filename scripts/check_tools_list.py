"""Smoke test: verify tools/list returns 6 L1+L2 tools, L3 gated.

Reads tools_list.out (produced by mcp-test.yml).
"""
import json
import sys
from pathlib import Path

path = Path(__file__).parent.parent / "tools_list.out"
if not path.exists():
    # Fall back to script dir (actions checkout root)
    path = Path("tools_list.out")
if not path.exists():
    sys.exit("FATAL: tools_list.out not found")

tools = []
for line in path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if isinstance(obj, dict) and obj.get("id") == 1 and "result" in obj and "tools" in obj.get("result", {}):
        tools = [t["name"] for t in obj["result"]["tools"]]
        break

print("tools:", tools)

expected = {
    "hl_health_check",
    "hl_search_knowledge",
    "hl_get_axis_detail",
    "hl_get_wellness_article",
    "hl_suggest_general_diet",
    "hl_suggest_general_motion",
}
missing = expected - set(tools)
assert not missing, f"missing L1/L2 tools: {missing}"

for private in ("hl_fusion_engine", "hl_risk_assess", "hl_tcm_constitution", "hl_evidence_grade"):
    assert private not in tools, f"L3 leaked without env flag: {private}"

print("OK: 6 L1+L2 tools, L3 gated")
