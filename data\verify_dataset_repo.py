#!/usr/bin/env python3
"""Verify that the remote lm203688/tcm-mkg tree matches the local corpus byte-for-byte.

Compares git blob SHA-1 (`sha1("blob <len>\\0" + content)`) of every local corpus file
against the blob sha recorded in the remote tree. Exit code 1 on any mismatch.

Usage:  python data/verify_dataset_repo.py
Auth:   $GH_PAT, or the cached PAT at .workbuddy/cache/gh_pat.txt
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER, REPO, BRANCH = "lm203688", "tcm-mkg", "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

# remote path in tcm-mkg -> local path in healthlens (None = generated card)
FILES: dict[str, str | None] = {
    "data/chp_entities.json": "data/tcm_mkg/chp_entities.json",
    "data/classical_books.json": "data/classical_books.json",
    "data/case_evidence_db.json": "data/case_evidence_db.json",
    "data/tcm_pathway_map.json": "data/tcm_pathway_map.json",
    "data/tcm_structured/神农本草经.json": "data/tcm_structured/神农本草经.json",
    "data/tcm_structured/食疗本草.json": "data/tcm_structured/食疗本草.json",
    "DATASET_CARD.md": "data/DATASET_CARD.md",
    "LICENSE": "LICENSE",
    "README.md": None,
}


def git_blob_sha(content: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def read_generated_readme() -> bytes:
    src = (ROOT / "data" / "publish_dataset_repo.py").read_text(encoding="utf-8")
    return src.split('HF_README = """')[1].split('"""')[0].encode("utf-8")


def api(path: str, token: str):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "healthlens-dataset-verify",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main() -> int:
    token = os.environ.get("GH_PAT") or (ROOT / ".workbuddy/cache/gh_pat.txt").read_text().strip()
    code, body = api("/git/trees/main?recursive=1", token)
    if code != 200:
        print(f"[FAIL] cannot read remote tree ({code})")
        return 1
    remote = {t["path"]: t["sha"] for t in json.loads(body)["tree"] if t["type"] == "blob"}
    print(f"remote blobs: {len(remote)}")

    failed = []
    for remote_path, local_path in FILES.items():
        content = read_generated_readme() if local_path is None else (ROOT / local_path).read_bytes()
        ok = git_blob_sha(content) == remote.get(remote_path)
        if not ok:
            failed.append(remote_path)
        print(f"  [{'OK  ' if ok else 'BAD '}] {remote_path}  ({len(content):,} bytes)")

    missing = sorted(set(FILES) - set(remote))
    print(f"\nmissing remotely: {missing or 'none'}")
    if failed or missing:
        print("Republish with: python data/publish_dataset_repo.py --push")
        return 1
    print("All corpus blobs match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
