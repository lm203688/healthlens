#!/usr/bin/env python
"""
Zenodo v2 (InvenioRDM) 一键上传脚本
适配 2023-10 之后新版 API：/api/deposit/depositions（旧 /api/uploads 已 404）

用法：
    python tools/zenodo_upload.py --token-file C:/Users/xing/.workbuddy/cache/zenodo_token.txt
或：
    set ZENODO_TOKEN=... && python tools/zenodo_upload.py

步骤：
    1. POST /api/deposit/depositions    → 创建 deposit（含 metadata）
    2. PUT  bucket_url/filename          → 上传二进制
    3. POST bucket_url/filename metadata → 登记 sha256/size（可选，Zenodo 会自动算）
    4. POST /depositions/{id}/actions/publish → 发布，返回 DOI

Dry-run：
    python tools/zenodo_upload.py --dry-run
跳过发布（只建 draft）：
    python tools/zenodo_upload.py --skip-publish
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = ROOT / "submissions" / "zenodo" / "zenodo_payload.json"
BASE = "https://zenodo.org/api"


def log(msg: str) -> None:
    print(f"[zenodo] {msg}", flush=True)


def load_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    if args.token_file:
        p = Path(args.token_file).expanduser()
        if not p.exists():
            sys.exit(f"Token file not found: {p}")
        return p.read_text(encoding="utf-8").strip()
    env = os.environ.get("ZENODO_TOKEN", "").strip()
    if env:
        return env
    sys.exit("No token provided. Use --token, --token-file, or $ZENODO_TOKEN.")


def step1_create_deposit(token: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Create a new deposition with metadata. Returns deposit JSON (id, links, pids)."""
    r = requests.post(
        f"{BASE}/deposit/depositions",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"metadata": metadata},
        timeout=60,
    )
    if r.status_code != 201:
        sys.exit(f"create deposit failed [{r.status_code}]: {r.text[:2000]}")
    return r.json()


def step2_upload_file(token: str, bucket_url: str, filename: str, file_path: Path) -> None:
    """Upload binary to the bucket with slash-safe filename."""
    url = f"{bucket_url}/{filename}"
    with file_path.open("rb") as f:
        r = requests.put(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
            },
            data=f,
            timeout=120,
        )
    if r.status_code not in (200, 201):
        sys.exit(f"upload failed [{r.status_code}] {filename}: {r.text[:500]}")


def step3_register_metadata(
    token: str, bucket_url: str, filename: str, checksum: str, size_bytes: int
) -> None:
    """Register file metadata. Best-effort: InvenioRDM bucket ignores POST metadata."""
    url = f"{bucket_url}/{filename}"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"checksum": checksum, "size": size_bytes},
        timeout=30,
    )
    if r.status_code not in (200, 201, 204):
        log(f"   warn: metadata registration for {filename} → {r.status_code} (ignored)")


def step4_publish(token: str, deposit_id: int) -> dict[str, Any]:
    r = requests.post(
        f"{BASE}/deposit/depositions/{deposit_id}/actions/publish",
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    if r.status_code != 202:
        sys.exit(f"publish failed [{r.status_code}]: {r.text[:1000]}")
    return r.json()


def flat_filename(path: str) -> str:
    """Zenodo bucket requires flat filenames; replace / with __."""
    return path.replace("/", "__")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="Zenodo API token")
    ap.add_argument("--token-file", help="Path to file containing the token")
    ap.add_argument("--dry-run", action="store_true", help="Only validate payload, do not upload")
    ap.add_argument("--skip-publish", action="store_true", help="Upload and register files, but do not publish")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep between file uploads")
    ap.add_argument("--dump-links", help="Dump deposit links to a JSON file for manual inspection")
    args = ap.parse_args()

    if not PAYLOAD_PATH.exists():
        sys.exit(f"Payload not found: {PAYLOAD_PATH}")
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    metadata = payload["metadata"]
    files = payload["attached_files"]

    log(f"Payload: {len(files)} files, prereserve_doi={metadata.get('prereserve_doi')}")
    lic = metadata.get('license')
    lic_id = lic.get('id') if isinstance(lic, dict) else lic
    log(f"License: {lic_id}")
    log(f"Version: {metadata.get('version')}")
    log(f"Creator: {metadata.get('creators', [{}])[0].get('name')}")

    # Pre-flight
    missing, mismatch = [], []
    total_bytes = 0
    for f in files:
        p = ROOT / f["path"]
        if not p.exists():
            missing.append(f["path"])
            continue
        data = p.read_bytes()
        total_bytes += len(data)
        actual = hashlib.sha256(data).hexdigest()
        if actual != f["sha256"]:
            mismatch.append(f["path"])
    log(f"Total size: {total_bytes/1e6:.2f} MB")
    if missing:
        sys.exit(f"Missing files ({len(missing)}): {missing[:5]}")
    if mismatch:
        sys.exit(f"SHA256 mismatch ({len(mismatch)}): {mismatch[:5]}")
    log("SHA256 pre-flight: all files match.")

    if args.dry_run:
        log("Dry-run complete.")
        return

    token = load_token(args)
    log(f"Token loaded: {token[:12]}...")

    # Step 1
    log("Step 1/4: create deposit...")
    dep = step1_create_deposit(token, metadata)
    deposit_id = dep["id"]
    bucket = dep["links"]["bucket"]
    prereq_doi = dep.get("metadata", {}).get("prereserve_doi", {}).get("doi") or dep.get("pids", {}).get("doi", "")
    log(f"   deposit_id={deposit_id}, prereq DOI={prereq_doi}")
    log(f"   bucket_url={bucket}")

    if args.dump_links:
        Path(args.dump_links).write_text(json.dumps(dep, indent=2), encoding="utf-8")

    # Step 2 & 3
    log(f"Step 2/4: uploading {len(files)} files...")
    for i, f in enumerate(files, 1):
        fname = flat_filename(f["path"])
        p = ROOT / f["path"]
        log(f"   [{i}/{len(files)}] {f['path']} ({p.stat().st_size/1e3:.0f} KB)")
        step2_upload_file(token, bucket, fname, p)
        # sha256 checksum Zenodo requires prefixed form
        checksum = f["sha256"]
        if not checksum.startswith("sha256:"):
            checksum = f"sha256:{checksum}"
        step3_register_metadata(token, bucket, fname, checksum, f["size_bytes"])
        time.sleep(args.sleep)

    if args.skip_publish:
        log("Step 4/4 SKIPPED (skip-publish). Draft at:")
        log(f"   https://zenodo.org/deposit/{deposit_id}")
        return

    # Step 4
    log("Step 4/4: publishing...")
    out = step4_publish(token, deposit_id)
    doi = out.get("doi") or prereq_doi
    html = f"https://zenodo.org/records/{deposit_id}"
    log("✅ Published!")
    log(f"   DOI:         {doi}")
    log(f"   Landing:     {html}")
    log(f"   JSON:        https://zenodo.org/api/records/{deposit_id}")


if __name__ == "__main__":
    main()
