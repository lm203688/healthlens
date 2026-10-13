"""生成知识语料的「可公开再分发」脱敏副本（S2-4 许可审计 · 方案 A）。

背景
----
`data/LICENSE_AUDIT_2026-10-13.md` 证实：古籍语料上游
`xiaopangxia/TCM-Ancient-Books` **无任何许可证**（GitHub API `license: null`，
`GET /license` 返回 404），按著作权法默认「保留所有权利」。
HealthLens 的派生数据虽为 MIT，但内嵌了上游文本的逐字摘录，
MIT 无法覆盖它覆盖不到的内容，因此这些文件不可整包公开发布。

本工具的作用
------------
生成一份**只含 HealthLens 自撰内容**的脱敏副本，可直接上 Zenodo：

- 剥离上游逐字摘录字段（`passage` / `source_quote` / `efficacy`）；
- 完整保留 HealthLens 自撰的 schema、ID、轴标注、关键词启发式结果；
- 在每份产物与清单中写入上游指针，便于使用者自查原文，但不搬运内容；
- **绝不修改源文件**：源数据只读，副本写入 `data/publishable/`，可随时重跑覆盖；
- **fail-loud**：写盘后回读校验，确认所有应剥离字段确已消失，否则抛错。

保守性说明
----------
`efficacy` 字段虽短（十余字），但实测就是从原文逐字复制的片段
（例：`一切气及香港脚∶取盐三升`），故默认一并剥离。
若后续向上游取得书面授权（审计方案 B），可用 `--keep-verbatim` 保留它。

用法
----
    python tools/redact_for_public_release.py            # 生成脱敏副本 + 清单
    python tools/redact_for_public_release.py --check    # 只校验，不写盘
    python tools/redact_for_public_release.py --keep-verbatim   # 保留 efficacy（需上游授权）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO / "data"
OUT_ROOT = REPO / "data" / "publishable"

# 上游出处指针：只记录「在哪里可自查」，不搬运任何内容。
UPSTREAM = {
    "repo": "https://github.com/xiaopangxia/TCM-Ancient-Books",
    "note": (
        "上游仓库未附带任何许可证（GitHub API license=null，GET /license 返回 404）。"
        "按著作权法默认保留所有权利。此处仅保留出处指针以便自查，本副本不含任何上游原文内容。"
    ),
    "evidence": "data/LICENSE_AUDIT_2026-10-13.md §2.2",
}

# 各来源中需剥离的上游逐字摘录字段。
STRIP_MAP = {
    # citation 是《太平御览》等上游原文的逐字引文（60/613 条、约 995 字），
    # 属著作权风险核心，必须剥离。历史缺陷：早期版本只剥 passage/efficacy，
    # 漏掉 citation 且校验器按配置自身核对而静默通过，导致逐字引文随产物发布。
    "classical_slices.json": {"container": "slices", "fields": ["passage", "efficacy", "citation"]},
}
# tcm_structured/ 下的每个文件共用同一结构。
TCM_STRUCTURED_FIELDS = ["source_quote", "efficacy"]

# 独立黑名单：不依赖 STRIP_MAP，任何情况下都不得出现在产物记录中。
# 存在意义是堵住「配置漏项 → 校验器按配置核对 → 静默通过」这条盲区。
# 若 STRIP_MAP 与它不一致，会在 _emit 里 assert 失败。
UPSTREAM_VERBATIM_FIELDS = frozenset({
    "passage", "efficacy", "citation", "source_quote",
})

# 授权保留：本轮明确许可保留的上游逐字字段。默认为空（全部剥离）。
# --keep-verbatim 只把 efficacy 加进来；这是「已剥离 / 已授权」二选一的
# 例外通道，而非绕过黑名单的后门——集合外的字段一律仍按黑名单拦截。
AUTHORIZED_RETENTION: set[str] = set()

# 经复核后**决定保留**的短书目元数据。保留理由必须写在产物里，
# 而不是伪装成「已剥离」——书名/药名/朝代属事实性数据，非创造性表达。
REVIEWED_RETAINED = {
    "classical_slices.json": ["book", "author", "dynasty", "entity", "entity_type", "property"],
}

REDACTION_NOTICE = {
    "redacted": True,
    "redaction_date": None,
    "reason": "上游古籍原文仓库无许可证（保留所有权利），逐字摘录字段不可再分发",
    "upstream": UPSTREAM,
    "license_of_retained_fields": "MIT (HealthLens 自撰派生结构)",
    "restoration": "取得上游书面授权后，用 --keep-verbatim 重跑可保留 efficacy 字段",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_record(record: dict, fields: list[str]) -> int:
    """剥离一条记录中的上游摘录字段，返回被剥离字段数。非破坏性。"""
    n = 0
    for f in fields:
        if f in record:
            record.pop(f)
            n += 1
    return n


def redact_classical_slices(write: bool) -> dict:
    src = SRC_ROOT / "classical_slices.json"
    doc = json.loads(src.read_text(encoding="utf-8"))
    cfg = STRIP_MAP["classical_slices.json"]
    out = {
        "meta": dict(doc["meta"]),
        "slices": [dict(s) for s in doc[cfg["container"]]],
    }
    removed = sum(strip_record(s, cfg["fields"]) for s in out["slices"])

    out["meta"]["redaction_notice"] = {
        **REDACTION_NOTICE,
        "redaction_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "fields_stripped": cfg["fields"],
        "authorized_retention": sorted(AUTHORIZED_RETENTION),
        "authorized_retention_rationale": (
            "efficacy 为上游原文短片段，仅在取得上游书面授权后由 --keep-verbatim 保留；"
            "未授权时该列表恒为空。" if AUTHORIZED_RETENTION else "无（全部剥离）"
        ),
        "records": len(out["slices"]),
        "fields_removed": removed,
        "retained_bibliographic": REVIEWED_RETAINED.get("classical_slices.json", []),
        "retained_bibliographic_rationale": (
            "book/author/dynasty/entity/entity_type/property 为书名、编者、朝代、药名等"
            "事实性书目数据（通常数十字节内），非创造性表达，经复核可随 MIT 发布。"
            "如上游要求删除，用 --strip-bibliographic 重跑。"
        ),
        "note": (
            "axis_hint / matched_keywords / axis_confidence 等字段为 HealthLens 自撰的"
            "关键词启发式标注（keyword_heuristic_v1），全部 needs_expert_review=true，"
            "非权威轴归属，可随 MIT 发布。"
        ),
    }
    return _emit(src, out, write, "classical_slices.json")


def redact_tcm_structured(write: bool) -> dict:
    """逐文件处理 data/tcm_structured/*.json。"""
    results = {}
    for src in sorted((SRC_ROOT / "tcm_structured").glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        out = {k: v for k, v in doc.items()}
        entities = [dict(e) for e in doc.get("entities", [])]
        removed = sum(strip_record(e, TCM_STRUCTURED_FIELDS) for e in entities)
        out["entities"] = entities

        # 保留 source_file 字段（仅文件名，非内容），指向上游出处。
        out["redaction_notice"] = {
            **REDACTION_NOTICE,
            "redaction_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "fields_stripped": TCM_STRUCTURED_FIELDS,
            "authorized_retention": sorted(AUTHORIZED_RETENTION),
            "records": len(entities),
            "fields_removed": removed,
            "upstream_file": doc.get("source_file"),
            "method": doc.get("method"),
        }
        results[src.name] = _emit(src, out, write, src.name, container="tcm_structured")
    return results


def _emit(src: Path, out: dict, write: bool, rel: str, container: str | None = None) -> dict:
    """写出产物（可选）并做 fail-loud 回读校验。"""
    text = json.dumps(out, ensure_ascii=False, indent=2)

    stat = {
        "source": str(src.relative_to(REPO)),
        "dest": f"data/publishable/{container + '/' if container else ''}{rel}",
        "source_sha256": sha256_of(src),
        "source_bytes": src.stat().st_size,
        "redacted_bytes": len(text.encode("utf-8")),
    }
    stat["bytes_saved_pct"] = round(
        (1 - len(text.encode("utf-8")) / stat["source_bytes"]) * 100, 1
    )

    if write:
        dest = OUT_ROOT / (f"{container}/" if container else "") / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 二进制写盘以保持 LF：text 已用 LF 序列化，Windows 下 write_text 会把
        # \n 转成 \r\n，使落盘字节比 redacted_bytes 多出换行数（实测
        # classical_slices.json 多 11,783 字节）。JSON 产物按跨平台惯例用 LF。
        dest.write_bytes(text.encode("utf-8"))
        stat["dest_sha256"] = sha256_of(dest)
        # fail-loud：报告的字节数必须等于落盘字节数。统计自欺是本轮事故的同源
        # 病灶（verbatim_chars_removed 曾在已剥离的记录上统计，恒为 0）。
        assert dest.stat().st_size == stat["redacted_bytes"], (
            f"{rel} 落盘 {dest.stat().st_size} 字节与报告 redacted_bytes "
            f"{stat['redacted_bytes']} 不符，字节统计不可信"
        )

    # --- 校验 1（配置驱动）：STRIP_MAP 声明剥离的字段必须真的消失。 ---
    want = STRIP_MAP.get(rel, {}).get("fields", TCM_STRUCTURED_FIELDS)
    container_key = STRIP_MAP.get(rel, {}).get("container", "entities")
    records = out.get(container_key, [])
    remaining = [
        f"{rec.get('slice_id') or rec.get('id') or rec.get('name')}:{f}"
        for rec in records
        for f in want
        if f in rec
    ]
    assert not remaining, f"脱敏失败，残留上游摘录字段: {remaining[:5]}"

    # --- 校验 2（独立黑名单）：不依赖 STRIP_MAP，防配置漏项。 ---
    # 例外通道：AUTHORIZED_RETENTION 里的字段是本轮明确授权保留的（--keep-verbatim
    # 且已获上游授权）。集合外的逐字字段只要残留在产物中就必须中断。
    unauthorized = AUTHORIZED_RETENTION - UPSTREAM_VERBATIM_FIELDS
    assert not unauthorized, (
        f"AUTHORIZED_RETENTION 试图豁免非上游逐字字段 {sorted(unauthorized)}；"
        "该集合只能收敛于 UPSTREAM_VERBATIM_FIELDS，不能当绕过黑名单的后门。"
    )
    enforced = UPSTREAM_VERBATIM_FIELDS - AUTHORIZED_RETENTION
    blacklisted = [
        f"{rec.get('slice_id') or rec.get('id') or rec.get('name')}:{f}"
        for rec in records
        for f in enforced
        if f in rec
    ]
    assert not blacklisted, (
        f"脱敏失败：产物含上游逐字字段但未被配置剥离（STRIP_MAP 漏项）: {blacklisted[:5]}"
    )

    # --- 校验 3（配置空转检测）：配置了剥离、源里却根本没有该字段。
    # 只告警不中断——该字段没剥等于没泄漏，不是脱敏失败；但配置里有脏项必须知道。
    # 注意不能 assert：黑名单是跨来源并集，某个来源的配置里天然可能不含其它来源的字段。
    source = json.loads(src.read_text(encoding="utf-8"))
    src_records = source.get(container_key, source.get("entities", []))
    inert = [
        f for f in want if src_records and not any(f in r for r in src_records)
    ]
    stat["inert_fields"] = inert

    stat["leaked_fields"] = 0
    stat["fields_stripped"] = want
    # 必须从**源记录**统计：产物里的字段已被剥离，在产物上量恒为 0（历史 bug）。
    stat["verbatim_chars_removed"] = sum(
        len(str(rec.get(f, ""))) for rec in src_records for f in want
    )
    stat["verbatim_chars_by_field"] = {
        f: sum(len(str(rec.get(f, ""))) for rec in src_records) for f in want
    }
    stat["retained_bibliographic"] = REVIEWED_RETAINED.get(rel, [])
    return stat


def write_manifest(stats: list[dict], write: bool) -> Path | None:
    manifest = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": "知识语料可公开再分发（Zenodo）脱敏副本清单",
        "audit": "data/LICENSE_AUDIT_2026-10-13.md",
        "upstream": UPSTREAM,
        "license_of_retained_fields": "MIT",
        "source_files_unchanged": True,
        "source_outputs": len(stats),
        "total_source_bytes": sum(s["source_bytes"] for s in stats),
        "total_redacted_bytes": sum(s["redacted_bytes"] for s in stats),
        "leaked_fields_total": sum(s["leaked_fields"] for s in stats),
        "outputs": stats,
    }
    path = OUT_ROOT / "REDACTION_MANIFEST.json"
    if write:
        OUT_ROOT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path if write else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成古籍语料可公开再分发脱敏副本")
    ap.add_argument("--check", action="store_true", help="只校验，不写盘")
    ap.add_argument(
        "--keep-verbatim",
        action="store_true",
        help="保留 efficacy（仅在已获上游书面授权时使用，见审计方案 B）",
    )
    ap.add_argument(
        "--strip-bibliographic",
        action="store_true",
        help="连 book/author/dynasty/entity 等书目元数据一并剥离（最保守，用于上游明确要求时）",
    )
    args = ap.parse_args(argv)

    if args.strip_bibliographic:
        for rel, bib in REVIEWED_RETAINED.items():
            STRIP_MAP.setdefault(rel, {"container": "entities", "fields": []})
            STRIP_MAP[rel]["fields"] = list(
                dict.fromkeys(STRIP_MAP[rel]["fields"] + bib)
            )
        REDACTION_NOTICE["reason"] += "；应上游要求，书目元数据亦已剥离"

    if args.keep_verbatim:
        # 只保留 efficacy（短片段），逐字引文类字段一个都不放。
        STRIP_MAP["classical_slices.json"]["fields"] = ["passage", "citation"]
        globals()["TCM_STRUCTURED_FIELDS"] = ["source_quote"]
        globals()["AUTHORIZED_RETENTION"] = {"efficacy"}
        REDACTION_NOTICE["reason"] = (
            "上游逐字摘录已剥离；efficacy 为短片段，作者声明已取得上游授权"
        )

    write = not args.check
    print("== 脱敏发布副本生成 ==")
    print(f"模式: {'--check 只校验' if args.check else '写盘到 data/publishable/'}"
          f"{'  [保留 efficacy]' if args.keep_verbatim else ''}")

    stats: list[dict] = []
    stats.append(redact_classical_slices(write))
    for name, st in redact_tcm_structured(write).items():
        stats.append(st)

    mp = write_manifest(stats, write)

    print()
    print(f"{'产物':46s} {'源字节':>9s} {'脱敏字节':>9s} {'省':>6s}")
    for s in stats:
        print(f"{Path(s['dest']).name:46s} {s['source_bytes']:>9,d} "
              f"{s['redacted_bytes']:>9,d} {s['bytes_saved_pct']:>5.1f}%")
    print(f"\n合计: {sum(s['source_bytes'] for s in stats):,} → "
          f"{sum(s['redacted_bytes'] for s in stats):,} 字节；"
          f"残留上游字段 {sum(s['leaked_fields'] for s in stats)} 个")
    if mp:
        print(f"清单: {mp.relative_to(REPO)}")
    print("\n源文件未被修改（只读处理）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
