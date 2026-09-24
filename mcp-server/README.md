# HealthLens MCP Server

MCP server exposing HealthLens wellness knowledge as tools for AI agents.

**Safe by default** — L1 (content) and L2 (general knowledge) tools only expose public wellness information. No personal health data. L3 (personalized) is opt-in via env var.

- Website: https://healthlens.cc
- Repository: https://github.com/lm203688/healthlens
- Design doc: `../docs/healthlens-mcp-design.md`

---

## Tools

### L1 — Content (always exposed)

| Tool | Purpose |
|---|---|
| `hl_health_check` | Service heartbeat & version |
| `hl_search_knowledge` | Search TCM knowledge base (TCM-MKG 6,207 herbs + classical books) |
| `hl_get_axis_detail` | Get one of the 8 axes explanation (A-H) |
| `hl_get_wellness_article` | Get metadata for a published wellness article |

### L2 — Knowledge (always exposed)

| Tool | Purpose |
|---|---|
| `hl_suggest_general_diet` | General diet guidance (anti_aging, energy_boost, anti_inflammatory, gut_health, sleep_improvement) |
| `hl_suggest_general_motion` | General exercise prescription (beginner/moderate/advanced) |

### L3 — Private (requires `HL_MCP_EXPOSE_PRIVATE=1`)

| Tool | Purpose |
|---|---|
| `hl_fusion_engine` | Eight-axis fusion reasoning for personalized recommendations |
| `hl_risk_assess` | ASCVD chronic disease risk assessment |
| `hl_tcm_constitution` | TCM constitution analysis |
| `hl_evidence_grade` | Evidence grading L1/L2/L3 |

---

## Quick Start

### Install

```bash
pip install healthlens
# Or from source:
git clone https://github.com/lm203688/healthlens
cd healthlens
pip install -e .
```

### Test

```bash
# Print tool list
python -m healthlens_agent mcp --demo

# JSON-RPC stdio mode (fallback)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m healthlens_agent mcp --jsonrpc
```

### Configure MCP Client

**Claude Desktop / Cursor / Cline / Cline / Windsurf**

Add to your MCP config (e.g. `~/.claude/mcp.json` or Cursor's `mcp.json`):

```json
{
  "mcpServers": {
    "healthlens": {
      "command": "python",
      "args": ["-m", "healthlens_agent", "mcp"],
      "env": {
        "HL_MCP_EXPOSE_PRIVATE": "0"
      }
    }
  }
}
```

For private tools:

```json
{
  "mcpServers": {
    "healthlens": {
      "command": "python",
      "args": ["-m", "healthlens_agent", "mcp"],
      "env": {
        "HL_MCP_EXPOSE_PRIVATE": "1"
      }
    }
  }
}
```

### Sample calls

```python
# Tool 1: Search TCM knowledge
{"name": "hl_search_knowledge", "arguments": {"query": "qi deficiency"}}

# Tool 2: Get axis explanation
{"name": "hl_get_axis_detail", "arguments": {"axis_id": "A"}}

# Tool 3: General diet suggestion
{"name": "hl_suggest_general_diet", "arguments": {"goal": "anti_aging"}}

# Tool 4: General motion prescription
{"name": "hl_suggest_general_motion", "arguments": {"intensity": "moderate"}}
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `HL_MCP_EXPOSE_PRIVATE` | `0` | Enable L3 (personalized) tools when set to `1` |
| `HL_MCP_OAUTH_ENABLED` | `0` | Enable OAuth auth for L3 tools (recommended for production) |
| `HL_MCP_RATE_LIMIT` | `100` | Per-user calls per minute |

---

## Data Boundaries (Red Lines)

**Never exposed through MCP:**

- User checkin records, bio-age, personalized recommendations
- User account credentials, payment info
- Chinese herb prescription (十八反十九畏 compatibility)
- Any output that could be construed as diagnosis

All L1/L2 tools return only public wellness knowledge from TCM-MKG (MIT license) and classical books.

---

## Disclaimer

HealthLens MCP provides general wellness information only, not medical advice. Consult a qualified healthcare professional for personal health decisions.

---

## License

MIT (see `../LICENSE`)

## Related

- HealthLens product: https://healthlens.cc
- Design doc: `../docs/healthlens-mcp-design.md`
- GOAI submission: https://healthlens.cc
