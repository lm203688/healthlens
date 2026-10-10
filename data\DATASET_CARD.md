# HealthLens TCM-MKG Structured Corpus

A curated, structured corpus of Traditional Chinese Medicine (TCM) knowledge for LLM training, RAG retrieval, and knowledge-graph research.

**Upstream source**: [TCM-MKG (GraphAI-for-TCM)](https://github.com/ZENGJingqi/GraphAI-for-TCM) · [Zenodo DOI 10.5281/zenodo.13763953](https://doi.org/10.5281/zenodo.13763953)

**Downstream consumer**: [HealthLens](https://healthlens.cc) MCP Server — this corpus is what powers `hl_search_knowledge`, `hl_get_axis_detail`, and (when enabled) `hl_tcm_constitution`.

## Distribution

| Channel | Location | How to load |
|---|---|---|
| **GitHub mirror (canonical)** | [lm203688/tcm-mkg](https://github.com/lm203688/tcm-mkg) | `git clone` / raw fetch, or the `datasets` snippets below |
| Hugging Face | one-click import from the GitHub mirror (see [publish_hf.py](publish_hf.py)) | `load_dataset("lm203688/tcm-mkg", data_files="data/chp_entities.json")` |
| Docker (MCP runtime) | `lm203688/healthlens-mcp` | `docker run -i --rm lm203688/healthlens-mcp` |
| Live HTTP endpoint | `https://healthlens.cc/api/v1/mcp` | JSON-RPC 2.0, no install |

Re-publish the mirror with `python data/publish_dataset_repo.py --push` (needs a PAT with `public_repo` scope); automate it via *Actions → Publish TCM corpus dataset*.

## Contents

| File | Records | Size | Description |
|---|---:|---:|---|
| `tcm_mkg/chp_entities.json` | 6,207 herb entities | 6.0 MB | Multi-dimensional herbal entities with ICD-11 / UMLS / MeSH / DOID alignment |
| `classical_books.json` | 701 classical entries | 131 KB | Structured excerpts from 神农本草经, 食疗本草, 本草纲目, 黄帝内经 |
| `case_evidence_db.json` | 120 case records | 95 KB | Evidence-graded case studies (L1/L2/L3 tiered) |
| `tcm_pathway_map.json` | 7 index entries | 6 KB | Pathway-to-entity lookup index |
| `tcm_structured/神农本草经.json` | Herbal compendium | 150 KB | Classical text with structure |
| `tcm_structured/食疗本草.json` | Dietary therapy | 94 KB | Dietary therapy compendium |

**Total**: ~6.5 MB, MIT-licensed, no PII, no PHI.

## Corpus statistics

- **6,207 herbal entities** — all `evidence_level: high`
- **~23,500 medicinal property records** across 3 dimensions:
  - `Medicinal flavor` — 9,024 (五味: sweet/sour/bitter/pungent/salty)
  - `Meridian tropism` — 8,292 (归经: which of the 12 meridians the herb affects)
  - `Therapeutic nature` — 6,201 (四气: warm/cool/cold/hot/neutral)
- Each property carries an `x_rank × y_rank` coordinate for downstream positioning on the flavor-nature matrix

## Entity schema (chp_entities.json)

```json
{
  "type": "herb_piece",
  "id": "CHP00001",
  "name": "阿尔泰多榔菊",
  "synonyms": ["多榔菊"],
  "pinyin": "a er tai duo lang ju",
  "english": "Doronicum altaicum",
  "sources": ["Viridiplantae"],
  "medicinal_properties": [
    {"CHP_ID": "CHP00001", "Medicinal_properties": "Sweet medicinal", "Class": "Medicinal flavor"},
    {"CHP_ID": "CHP00001", "Medicinal_properties": "Lung meridian", "Class": "Meridian tropism"},
    {"CHP_ID": "CHP00001", "Medicinal_properties": "Warm therapeutic", "Class": "Therapeutic nature"}
  ],
  "evidence_level": "high",
  "provenance": "TCM-MKG v3"
}
```

Key fields:
- **id** — stable entity identifier (CHP##### prefix for herbs, similar prefixes for other types)
- **name** — canonical Chinese name
- **synonyms** — alternate names (needed for fuzzy matching)
- **pinyin** — romanized pronunciation
- **english** — Latin/Western botanical name
- **medicinal_properties** — 4D tensor: `Medicinal_properties × Class × x_rank × y_rank`
- **evidence_level** — `high` / `medium` / `low` — HealthLens-specific grading
- **provenance** — version stamp for downstream reproducibility

## Downstream standard alignment

Each entity is aligned to 4 international standards:

- **ICD-11** (World Health Organization) — disease/condition codes
- **UMLS** (Unified Medical Language System) — NLM terminology
- **MeSH** (Medical Subject Headings) — PubMed indexing
- **DOID** (Disease Ontology) — disease identifiers

This alignment is the primary data moat — reproducing it requires both the upstream graph and the alignment work HealthLens did in v3.

## Usage in HealthLens

The corpus is bundled read-only in the [HealthLens MCP Server](../mcp-server/) Docker image. Tools that consume it:

- `hl_search_knowledge` — semantic search over herbs + classical books
- `hl_get_axis_detail` — serves axis A-H mechanism explanations
- `hl_tcm_constitution` — (L3, private) constitution analysis grounded on this corpus

## Citing

```bibtex
@dataset{healthlens_tcm_mkg,
  title   = {HealthLens TCM-MKG Structured Corpus},
  author  = {HealthLens contributors},
  year    = {2026},
  url     = {https://github.com/lm203688/tcm-mkg},
  note    = {Curated from TCM-MKG (Zenodo 10.5281/zenodo.13763953), evidence-graded by HealthLens}
}
```

## License

MIT. Upstream TCM-MKG is MIT (Copyright (c) 2024 Zeng Jingqi). HealthLens evidence-level grading is also MIT.

---

**Maintainer**: HealthLens team — https://github.com/lm203688/healthlens

**Update frequency**: evidence grading refreshed monthly; entity additions upstream-driven.

**Feedback**: open a GitHub issue labeled `dataset`.
