# HealthLens System Card

Version: v0.30.0  ·  Date: 2026-10-18  ·  Companion to `docs/model_card.md`

> **Not a medical device.** HealthLens is a wellness framework. Nothing in
> this system card is a diagnostic, therapeutic, or predictive medical claim.

The model card describes the eight-axis scoring engine in isolation. This
**system card** describes the full delivered system: engine + API + SDK +
edge gateway + A2A agent + MCP tool server + partner tier + deployment
topology + operational telemetry. Format is inspired by ISO/IEC 5259
(AI system lifecycle) and the OWASP AI Security Top 10.

---

## 1. System Composition

```
                        ┌─────────────────────────┐
                        │  User / Client (web,    │
                        │  partner API, MCP)      │
                        └──────────┬──────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │              FastAPI Backend            │
              │  /api/v1/* / /api/v1/mcp / /api/v1/a2a │
              └──────┬───────────────────────┬─────────┘
                     │                       │
       ┌─────────────┴──────┐      ┌─────────┴─────────────┐
       │  Eight-axis engine │      │  L1-L4 science layer   │
       │  fusion_engine.py  │      │  dowhy / nof-one /     │
       │  axis_scorers.py   │      │  bandit / graphrag /   │
       │  tcm_safety.py     │      │  rubric / ts_series    │
       └────────────────────┘      └─────────────────────────┘
                     │                       │
       ┌─────────────┴──────┐      ┌─────────┴─────────────┐
       │  SQLite (dev) /    │      │  Redis (nonce dedup,   │
       │  Postgres (prod)   │      │  rate-limit, sessions) │
       └────────────────────┘      └─────────────────────────┘

       Edge path:
       ┌──────────────┐     BLE/Wi-Fi      ┌──────────────────┐
       │  Muse / HRV  │ ─────────────────> │  Raspberry Pi    │
       │  sensor      │                    │  healthgateway   │
       └──────────────┘                    │  Goertzel FFT    │
                                           └────────┬─────────┘
                                                    │ POST /device-metrics
                                                    ▼
                                           ┌──────────────────┐
                                           │  FastAPI backend │
                                           └──────────────────┘
```

### 1.1 Components

| Component | Location | Purpose |
|---|---|---|
| Eight-axis engine | `app/lib/fusion_engine.py`, `app/core/axis_scorers.py` | Core scoring logic |
| TCM safety guard | `app/core/tcm_safety.py` | Jurisdiction + wellness-language filter |
| Compliance gate | `app/core/compliance/gb2001.py` | GB/T 20001.10-2014 clause mapping |
| National standard gate | `app/lib/national_standard_gate.py` | Runtime guard for GB/T 20348-2026 |
| Causal adapter | `app/lib/dowhy_adapter.py` | DoWhy optional adapter |
| N-of-1 statistics | `app/lib/nof_one_effect.py` | Bootstrap + E-value |
| Safety bandit | `app/lib/safety_bandit.py` | LinUCB + SafetyMask |
| GraphRAG engine | `app/lib/graphrag_engine.py` | 1661 nodes / 2005 edges |
| GraphRAG security | `app/lib/graphrag_security.py` | GraphExtractionDefender |
| A2A agent | `app/api/a2a.py`, `app/lib/a2a_task_store.py` | A2A v1.0.1 JSON-RPC |
| MCP server | `app/mcp_server.py` | MCP 2026-07-28 protocol |
| Powered-by SDK | `app/integrations/sdk/` | Async client + API key + remote config |
| Partner API | `app/api/partners.py`, `app/api/partner_api.py` | B2B tier |
| Edge gateway | `edge/healthgateway/` | Raspberry Pi firmware + Goertzel FFT |

## 2. Deployment Topology

| Layer | Where | Notes |
|---|---|---|
| Frontend | Cloudflare Pages (`healthlens-a3w.pages.dev`) | React + react-i18next |
| Backend | Aliyun ECS 150.158.119.19 (Ubuntu + Docker) | Docker Compose, single web container |
| Edge gateway | Raspberry Pi at user site | BLE/Wi-Fi sensor ingestion |
| Federated coordination | Local (in-process Flower adapter) | No external federation host in current release |

## 3. Security Controls

### 3.1 Data protection

- **Data residency**: A4 region guard restricts cross-jurisdiction data flow
  at the API layer.
- **PII**: GDPR-consent-persisted fields (`consent_version`, `consent_scope`,
  `consent_timestamp`) on every user record.
- **Nonce dedup**: Redis `SET NX EX` for idempotent writes (survives multi-worker).
- **Rate limit**: Redis-backed per-key rate limiter on all write endpoints.
- **Auth**: JWT Bearer tokens, refresh rotation on access token expiry.
- **CORS**: production CORS locked to allow-list domains.

### 3.2 Compliance

- **Wellness language scrub**: symptom and recommendation text is
  systematically stripped of disease-hint terms and cure-implication phrases
  (see test_claims_engine.py gate).
- **Jurisdiction-aware thresholds**: `config/axis_thresholds.yaml` and
  `config/national_standards.json` are keyed by jurisdiction (`cn`/`us`/`eu`).
- **GB/T 20348-2026 mapping**: `app/core/compliance/gb2001.py` maps each
  engine output to a GB/T clause for Chinese-market disclosures.
- **GraphRAG defender**: `app/lib/graphrag_security.py` masks sensitive
  fields and caps sample size on graph queries.

### 3.3 Failure modes and mitigations

| Failure mode | Detection | Mitigation |
|---|---|---|
| Missing critical biomarker | Axis scorer returns `unmeasured` | Recommendation library omits axis-dependent recs |
| Knowledge base missing (pulse) | `PulseKnowledgeBaseError` | 503 response, no fallback fabricate |
| Heavy library (DoWhy/Flower/PyMC) not installed | `try/except ImportError` | `HealthLensUnavailableEngine` |
| Multi-worker nonce collision | Redis `SET NX EX` | 409 conflict, client retries |
| Graph extraction attack | GraphExtractionDefender + sample cap | Masked fields, truncated response |
| Adversarial input | `_clamp` in all scorers | Scores remain in [0, 100] |

## 4. Operational Telemetry

- **CI**: GitHub Actions, `ci.yml`, federated extra, mypy gate, pytest gate,
  sync_test_count --check gate.
- **Releases**: manual dispatch via workflow `deploy-frontend.yml` (id 362982805)
  for frontend; Docker image rebuild for backend.
- **Version**: single source of truth in `pyproject.toml`, synced to
  `agent-card.json` via `tools/sync_version.py`.
- **Test count**: single source of truth in `submissions/medrxiv/submission_manifest.json`,
  synced by `tools/sync_test_count.py --apply --pytest-out pytest.out`.
- **Deployment audit**: `container_mount_audit.md` documents every bind
  mount; `verify_container_mounts.py` enforces in CI.

## 5. Post-Deployment Monitoring

Not yet implemented. The L4 evaluation layer (`app/api/evaluation.py`,
`app/lib/rubric_engine.py`) is scaffolded with a 200-item rubric benchmark
but production traffic is required to be meaningful. This is a known gap
and is called out in Section 8 (Limitations) of the paper.

## 6. Compliance with Reporting Standards

| Standard | Coverage |
|---|---|
| DECIDE-AI | 19 / 19 (16 S + 3 P, 0 M) |
| TRIPOD-AI | 21 / 21 (19 S + 2 P, 0 M) |
| SPIRIT-AI | 12 / 12 (11 S + 1 P, 0 M) |
| GB/T 20348-2026 | Full clause mapping in `app/core/compliance/gb2001.py` |
| A2A v1.0.1 | Agent card published, JSON-RPC endpoint live |
| MCP 2026-07-28 | Full protocol conformance |

Full audit in `data/CHECKLIST_COMPLIANCE_REPORT.md` (auto-generated).

## 7. Limitations of this Card

- **No production telemetry yet** — Section 5 above is aspirational.
- **No cross-population discrimination testing** — evaluation data is synthetic.
- **No fuzzing** — adversarial battery is hand-designed, not mutation-based.
- **No multi-region HA** — single-ECS deployment; HA is on the roadmap.

## 8. Contact

See `docs/model_card.md` Section 7 for contact details.
