"""Smoke test: verify mcp-server/server.json is a valid MCP server manifest."""
import json
from pathlib import Path

path = Path("mcp-server/server.json")
if not path.exists():
    path = Path(__file__).parent.parent / "mcp-server" / "server.json"

data = json.loads(path.read_text())

assert data.get("$schema", "").startswith("https://static.modelcontextprotocol.io"), "missing/invalid $schema"
assert data["name"].startswith("io.github.lm203688/"), f"bad name: {data.get('name')}"
assert data["version"], "missing version"
assert data["repository"]["url"].startswith("https://github.com/lm203688/"), "bad repo url"

pkg = data["packages"][0]
assert pkg["registryType"] == "pypi", "must publish to PyPI"
assert pkg["transport"]["type"] == "stdio", "must be stdio transport"
assert pkg["identifier"] == "healthlens", f"expected identifier=healthlens, got {pkg['identifier']}"

print(f"OK: server.json valid — {data['name']} v{data['version']}")
