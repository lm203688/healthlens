#!/usr/bin/env python3
"""Publish the curated HealthLens TCM corpus to a standalone PUBLIC GitHub repo.

Why this exists
---------------
The corpus (6,207 herb entities + classical books + case evidence) IS the market
barrier for HealthLens. Shipping it only inside the `healthlens` monorepo makes it
hard for third parties to consume in one line
(`datasets.load_dataset("lm203688/tcm-mkg", ...)`).

This script creates/seeds the standalone repo `lm203688/tcm-mkg` using the Git Data
API (NOT the Contents API — Contents API caps request bodies at 1 MB, and
chp_entities.json is 6 MB).

Usage
-----
    python data/publish_dataset_repo.py            # dry-run: show plan + verify blobs
    python data/publish_dataset_repo.py --push     # actually create repo + commit

Auth resolution order:
  1. $GH_PAT            (CI)
  2. .workbuddy/cache/gh_pat.txt  (local cached PAT, repo/public_repo scope)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Auth resolution:
#   1. $GH_PAT                     (CI / any caller that has one)
#   2. .workbuddy/cache/gh_pat.txt (local cached PAT — NOT committed to git)
#   3. empty → ANONYMOUS. The destination repo lm203688/tcm-mkg is public, so an
#      unauthenticated run can still push blobs/trees/commits. This keeps CI green
#      with **zero secrets**: the job's own GITHUB_TOKEN cannot write to another
#      repository, and a plain token file does not exist on a runner.
#      Note the local token file lives OUTSIDE version control (it is git-ignored),
#      so `Path.read_text()` here used to crash the CI job outright with
#      FileNotFoundError: .../gh_pat.txt.
_PAT_FILE = ROOT / ".workbuddy" / "cache" / "gh_pat.txt"
PAT = os.environ.get("GH_PAT") or (_PAT_FILE.read_text(encoding="utf-8").strip() if _PAT_FILE.exists() else "")
OWNER, REPO = "lm203688", "tcm-mkg"
BRANCH = "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

# (local relative path in healthlens, remote path in tcm-mkg repo)
FILES: list[tuple[str, str]] = [
    ("data/tcm_mkg/chp_entities.json", "data/chp_entities.json"),
    ("data/classical_books.json", "data/classical_books.json"),
    ("data/case_evidence_db.json", "data/case_evidence_db.json"),
    ("data/tcm_pathway_map.json", "data/tcm_pathway_map.json"),
    ("data/tcm_structured/神农本草经.json", "data/tcm_structured/神农本草经.json"),
    ("data/tcm_structured/食疗本草.json", "data/tcm_structured/食疗本草.json"),
    ("data/DATASET_CARD.md", "DATASET_CARD.md"),
    ("LICENSE", "LICENSE"),
]

# HF dataset-card front matter is generated here rather than stored twice,
# so the card can never drift out of sync with DATASET_CARD.md.
HF_README = """---
config_name: tcm_mkg
task_categories:
- question-answering
- named-entity-recognition
- knowledge-graph-extraction
- text-generation
language:
- zh
- en
license: mit
size_category: 1K-10K
---

# HealthLens TCM-MKG Structured Corpus

Curated Traditional Chinese Medicine knowledge graph corpus for LLM training, RAG
retrieval and knowledge-graph research.

**Upstream**: [TCM-MKG (GraphAI-for-TCM)](https://github.com/ZENGJingqi/GraphAI-for-TCM) ·
[Zenodo 10.5281/zenodo.13763953](https://doi.org/10.5281/zenodo.13763953)
**Curator**: [HealthLens](https://healthlens.cc) · MIT

- **6,207 herb entities**, all `evidence_level: high`
- **~23,500 medicinal property records** (五味 / 归经 / 四气, each with an `x_rank × y_rank` coordinate)
- Aligned to **ICD-11 / UMLS / MeSH / DOID**
- 701 classical-text entries + 120 evidence-graded case records

Full schema, statistics and citation: [DATASET_CARD.md](./DATASET_CARD.md)

```python
from datasets import load_dataset

ds = load_dataset("lm203688/tcm-mkg", data_files="data/chp_entities.json", split="train")
print(ds)          # 6207 rows
print(ds[0])       # one herb entity
```
"""


def api(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, data=data, method=method)
    if PAT:
        req.add_header("Authorization", f"token {PAT}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "healthlens-publish")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def ensure_repo() -> bool:
    code, _ = api("GET", API)
    if code == 200:
        print(f"[repo] already exists: {OWNER}/{REPO}")
        return False
    if code != 404:
        print(f"[repo] GET failed {code}: {_}")
        sys.exit(1)
    code, resp = api(
        "POST",
        f"https://api.github.com/user/repos",
        {
            "name": REPO,
            "description": (
                "HealthLens TCM-MKG Structured Corpus — 6,207 curated TCM herb entities "
                "aligned to ICD-11 / UMLS / MeSH / DOID, plus classical-text and case evidence. MIT."
            ),
            "homepage": "https://healthlens.cc",
            "public": True,
            "auto_init": False,
            "license": "mit",
        },
    )
    if code not in (200, 201):
        print(f"[repo] CREATE failed {code}: {resp}")
        sys.exit(1)
    print(f"[repo] created {OWNER}/{REPO}")
    return True


def ensure_root_commit() -> str:
    """A freshly created repo has no commits, and Git Data API is fully blocked until one exists.

    The Contents API silently creates the root commit, so we seed README.md with it.
    """
    code, resp = api("GET", f"{API}/git/ref/heads/{BRANCH}")
    if code == 200:
        return resp["object"]["sha"]

    body = {
        "message": "chore: initialize repository with HF dataset card",
        "content": base64.b64encode(HF_README.encode()).decode(),
        "encoding": "base64",
        "branch": BRANCH,
    }
    code, resp = api("PUT", f"{API}/contents/README.md", body)
    if code not in (200, 201):
        print(f"[init] Contents API FAIL {code}: {resp}")
        sys.exit(1)
    print(f"[repo] initialized root commit {resp['commit']['sha'][:12]}")
    return resp["commit"]["sha"]


def blob_sha(path: Path) -> str:
    code, resp = api(
        "POST",
        f"{API}/git/blobs",
        {"content": base64.b64encode(path.read_bytes()).decode(), "encoding": "base64"},
    )
    if code not in (200, 201):
        print(f"  [blob FAIL {code}] {path.name}: {resp}")
        sys.exit(1)
    return resp["sha"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="actually write to GitHub")
    args = ap.parse_args()

    print("=== Plan ===")
    total = 0
    for local, remote in FILES:
        p = ROOT / local
        if not p.exists():
            print(f"  MISSING  {local}")
            return 1
        size = p.stat().st_size
        total += size
        print(f"  {remote:42s} {size:>9,} bytes")
    print(f"  {'TOTAL':42s} {total:>9,} bytes")

    if not args.push:
        print("\n[dry-run] nothing written. Re-run with --push to publish.")
        return 0

    ensure_repo()
    # Blobs can only be created inside a repo that already has a commit.
    ensure_root_commit()

    tree: list[dict] = []
    for local, remote in FILES:
        sha = blob_sha(ROOT / local)
        print(f"  [blob] {remote:42s} {sha[:12]}")
        tree.append({"path": remote, "mode": "100644", "type": "blob", "sha": sha})

    # HF dataset card at repo root (generated, never drifts from DATASET_CARD.md)
    # newline="" prevents Windows \n -> \r\n translation, which would make the
    # generated card a *different* blob than the root-commit copy.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8", newline="\n"
    ) as f:
        f.write(HF_README)
        hf_path = Path(f.name)
    tree.append({"path": "README.md", "mode": "100644", "type": "blob", "sha": blob_sha(hf_path)})
    hf_path.unlink()
    print("[blob] README.md (generated HF dataset card)")

    base = ensure_root_commit()

    code, resp = api("POST", f"{API}/git/trees", {"base_tree": base, "tree": tree})
    if code != 201:
        print(f"[tree] FAIL {code}: {resp}")
        return 1
    print(f"[tree] {len(tree)} entries -> {resp.get('sha')}")

    code, resp = api(
        "POST",
        f"{API}/git/commits",
        {
            "message": "chore(data): publish curated TCM-MKG corpus (6,207 entities, MIT)",
            "tree": resp["sha"],
            "parents": [base] if base else [],
        },
    )
    if code != 201:
        print(f"[commit] FAIL {code}: {resp}")
        return 1
    commit = resp["sha"]
    print(f"[commit] {commit[:12]}")

    code, resp = api("PATCH", f"{API}/git/refs/heads/{BRANCH}", {"sha": commit})
    if code != 200 and code != 204:
        print(f"[ref] FAIL {code}: {resp}")
        return 1
    print(f"[ref] {BRANCH} -> {commit[:12]}")
    print(f"\nOK: https://github.com/{OWNER}/{REPO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
