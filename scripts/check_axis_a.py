"""Smoke test: verify hl_get_axis_detail call returns axis A payload."""
import json
import sys
from pathlib import Path

path = Path(__file__).parent.parent / "axis_a.out"
if not path.exists():
    path = Path("axis_a.out")
if not path.exists():
    sys.exit("FATAL: axis_a.out not found")

matched = False
for line in path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if obj.get("id") == 2 and "result" in obj:
        content = json.loads(obj["result"]["content"][0]["text"])
        assert content["axis_id"] == "A", f"axis_id != A: {content['axis_id']}"
        assert "mechanism" in content, "missing mechanism field"
        assert "disclaimer" in content, "missing disclaimer field"
        matched = True
        print("OK: axis A returned with mechanism + disclaimer")
        break

if not matched:
    sys.exit("FATAL: no matching response for id=2")
