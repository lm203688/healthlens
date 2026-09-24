# HealthLens MCP Marketplace Submissions — Copy-Paste Ready

Fill these directly into Glama / Official MCP Registry / Smithery / mcp.so / PulseMCP.

---

## 1. Glama (glama.ai/mcp) — 30 min

### Form Fields

- **Name**:`HealthLens Wellness Knowledge`
- **Repository**:`https://github.com/lm203688/healthlens`
- **Website**:`https://healthlens.cc`
- **Description** (copy from `mcp-server/server.json`):

> MCP server exposing HealthLens wellness knowledge: 8-axis integrative framework explanations, TCM knowledge base search (TCM-MKG graph with 6,207 herbs), general diet & motion guidance, and optional personalized fusion reasoning (private mode). L1 (content) and L2 (general knowledge) tools are safe by default with no personal data exposure; L3 (personalized reasoning) is opt-in via HL_MCP_EXPOSE_PRIVATE=1. Covers hl_health_check, hl_search_knowledge, hl_get_axis_detail, hl_get_wellness_article, hl_suggest_general_diet, hl_suggest_general_motion, plus private hl_fusion_engine, hl_risk_assess, hl_tcm_constitution, hl_evidence_grade.

- **Install**:`pip install healthlens`
- **Transport**:stdio
- **Categories**:health, wellness, integrative-medicine, tcm, personalized-medicine
- **License**:MIT

---

## 2. Official MCP Registry (github.com/modelcontextprotocol/servers)

**Submit a PR to add this server under `src/health/healthlens.md`:**

```markdown
---
title: HealthLens Wellness Knowledge
author: HealthLens
repository: https://github.com/lm203688/healthlens
license: MIT
install: pip install healthlens
---

# HealthLens Wellness Knowledge

MCP server exposing HealthLens wellness knowledge for AI agents. Safe by
default — L1 (content) and L2 (general knowledge) tools only expose public
wellness information, no personal health data. L3 (personalized reasoning)
is opt-in via `HL_MCP_EXPOSE_PRIVATE=1`.

## Tools

- `hl_health_check` — service heartbeat
- `hl_search_knowledge` — TCM knowledge base search (6,207 herbs, classical books)
- `hl_get_axis_detail` — 8-axis framework explanation (A-H)
- `hl_get_wellness_article` — published article metadata
- `hl_suggest_general_diet` — general diet guidance
- `hl_suggest_general_motion` — general exercise prescription

Private (opt-in):
- `hl_fusion_engine` — personalized 8-axis fusion reasoning
- `hl_risk_assess` — ASCVD risk assessment
- `hl_tcm_constitution` — TCM constitution analysis
- `hl_evidence_grade` — evidence grading L1/L2/L3

## Website

https://healthlens.cc

## License

MIT
```

**PR title**: `Add HealthLens wellness MCP server`

---

## 3. Smithery (smithery.ai)

- Sign in with GitHub → `lm203688`
- Add server → point to `https://github.com/lm203688/healthlens`
- Manifest path: `mcp-server/server.json`
- Install: `pip install healthlens`

Smithery auto-parses `server.json`. No form filling required.

---

## 4. mcp.so

- **Name**:`HealthLens`
- **Repo**:`https://github.com/lm203688/healthlens`
- **Description**: same as Glama (see above)
- **Install**:`pip install healthlens`

---

## 5. PulseMCP (pulsemcp.com)

- **Server name**:`HealthLens Wellness Knowledge`
- **GitHub**:`https://github.com/lm203688/healthlens`
- **Description**: same as Glama
- **Install**:`pip install healthlens`

---

## 6. PyPI publish (needs user credentials)

Package name `healthlens` is currently unclaimed (verified 2026-09-24):
`https://pypi.org/simple/healthlens/` → 404

**Steps (user)**:
1. Go to https://pypi.org/manage/account/token/ and create an API token (scope: entire account or just `healthlens`)
2. Copy the token (starts with `pypi-pypi-`)
3. In GitHub repo Settings → Secrets and variables → Actions → New repository secret
   - **Name**: `PYPI_API_TOKEN`
   - **Value**: `pypi-pypi-...`
4. Go to Actions tab → "Publish to PyPI" workflow → Run workflow → check `dry_run`
   - First run: `dry_run=true` to validate
   - Second run: `dry_run=false` to publish
5. Or wait for a GitHub Release to be published — the workflow auto-triggers

**Alternative** (local):
```bash
pip install build twine
python -m build
python -m twine upload dist/*
```

---

## 7. Marketplace summary dashboard

After submissions, paste this in your personal tracker:

| Market | URL | Status | Submitted | Live URL |
|---|---|---|---|---|
| Glama | https://glama.ai/mcp | ⏳ | | |
| Official Registry | https://github.com/modelcontextprotocol/servers | ⏳ | | |
| Smithery | https://smithery.ai | ⏳ | | |
| mcp.so | https://mcp.so | ⏳ | | |
| PulseMCP | https://pulsemcp.com | ⏳ | | |
| PyPI | https://pypi.org/project/healthlens | ⏳ | | |
