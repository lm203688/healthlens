"""Smoke test: verify hl_search_knowledge call returns a result."""
import json
import sys
from pathlib import Path

path = Path(__file__).parent.parent / "search.out"
if not path.exists():
    path = Path("search.out")
if not path.exists():
    sys.exit("FATAL: search.out not found")

matched = False
for line in path.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if obj.get("id") == 3 and "result" in obj:
        content = json.loads(obj["result"]["content"][0]["text"])
        # Should be a dict with results list (may be empty, that's fine)
        assert isinstance(content, dict), "search result must be a dict"
        matched = True
        print(f"OK: hl_search_knowledge returned keys={list(content.keys())}")
        break

if not matched:
    sys.exit("FATAL: no matching response for id=3")
