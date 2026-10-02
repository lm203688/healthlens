#!/usr/bin/env python3
"""Publish the curated TCM corpus to Hugging Face as a dataset.

The corpus is already mirrored on GitHub: https://github.com/lm203688/tcm-mkg
`huggingface_hub` can import it in one click. This script does the same thing
programmatically so it can run from CI.

Usage:
    pip install huggingface_hub
    export HF_TOKEN=hf_xxxxx                       # write access
    python data/publish_hf.py                      # create repo + upload (idempotent)
    python data/publish_hf.py --private            # keep it private
    python data/publish_hf.py --parquet            # also emit parquet splits
    python data/publish_hf.py --dry-run            # plan only

If huggingface_hub is not installed, the script prints the one-click GitHub import
URL instead of failing, so there is always a path forward.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ID = "lm203688/tcm-mkg"
HF_UPLOADS = [
    ("data/tcm_mkg/chp_entities.json", "data/chp_entities.json"),
    ("data/classical_books.json", "data/classical_books.json"),
    ("data/case_evidence_db.json", "data/case_evidence_db.json"),
    ("data/tcm_pathway_map.json", "data/tcm_pathway_map.json"),
    ("data/tcm_structured/神农本草经.json", "data/tcm_structured/神农本草经.json"),
    ("data/tcm_structured/食疗本草.json", "data/tcm_structured/食疗本草.json"),
    ("data/DATASET_CARD.md", "README.md"),
    ("LICENSE", "LICENSE"),
]
GITHUB_MIRROR = "https://github.com/lm203688/tcm-mkg"


def load_hub():
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print("huggingface_hub not installed.")
        print("  pip install huggingface_hub")
        print("\nOne-click alternative (no install needed) — import the GitHub mirror:")
        print("  https://huggingface.co/new/dataset?repo_id=" + REPO_ID.replace("/", "%2F"))
        print(f"  then point the importer at {GITHUB_MIRROR}")
        return None
    from huggingface_hub import HfApi, create_repo

    return HfApi(), create_repo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--parquet", action="store_true", help="convert JSON to parquet splits")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=== Plan ===")
    total = 0
    for local, remote in HF_UPLOADS:
        p = ROOT / local
        if not p.exists():
            print(f"  MISSING {local}")
            return 1
        total += p.stat().st_size
        print(f"  {remote:38s} {p.stat().st_size:>9,}")
    if args.parquet:
        print("  (+ parquet conversion)")
    print(f"  {'TOTAL':38s} {total:>9,}")
    if args.dry_run:
        print("\n[dry-run] nothing uploaded.")
        return 0

    hub = load_hub()
    if hub is None:
        return 2
    api, create_repo = hub

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN not set. Create one at https://huggingface.co/settings/tokens")
        return 2

    create_repo(
        REPO_ID,
        repo_type="dataset",
        private=args.private,
        exist_ok=True,
        token=token,
    )
    print(f"[repo] {REPO_ID}")

    for local, remote in HF_UPLOADS:
        api.upload_file(
            path_or_fileobj=str(ROOT / local),
            path_in_repo=remote,
            repo_id=REPO_ID,
            repo_type="dataset",
            token=token,
        )
        print(f"  [upload] {remote}")

    if args.parquet:
        try:
            import pyarrow.json as pyjson
            import pyarrow.parquet as pq
        except ImportError:
            print("  [skip] pyarrow not installed — run: pip install pyarrow")
        else:
            out = ROOT / ".cache_hf_parquet" / "tcm_mkg" / "data"
            out.mkdir(parents=True, exist_ok=True)
            src = ROOT / "data/tcm_mkg/chp_entities.json"
            table = pyjson.read_json(src)
            pq.write_table(table, out / "data.parquet")
            api.upload_file(
                path_or_fileobj=str(out / "data.parquet"),
                path_in_repo="data/tcm_mkg/data.parquet",
                repo_id=REPO_ID,
                repo_type="dataset",
                token=token,
            )
            print(f"  [parquet] data/tcm_mkg/data.parquet ({table.num_rows} rows)")

    print(f"\nOK: https://huggingface.co/datasets/{REPO_ID}")
    print("Load with:")
    print('    from datasets import load_dataset')
    print(f'    load_dataset("{REPO_ID}", data_files="data/chp_entities.json")')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
