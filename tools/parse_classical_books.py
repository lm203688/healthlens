# -*- coding: utf-8 -*-
"""解析中医古籍 txt 合集的书目元数据。

源语料格式（gb18030 编码），每部开头带固定字段::

    <篇名>神农本草经
    书名：神农本草经
    作者：孙星衍
    朝代：清
    年份：公元1644-1911年

输出 books.json（UTF-8），供 import_classical_books.py 入库。
只抽取原文明确写出的字段，缺失即留空——不推断、不编造。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any

SRC_DIR = os.path.join("中医", "中医古籍txt合集")
OUT_PATH = os.path.join("data", "classical_books.json")

# 分类规则按优先级排列：先命中者为准。
# 依据书名关键词，覆盖中医目录学常见类目。
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("食疗", ("食疗", "食治", "饮膳", "食物本草", "食鉴", "调疾饮食")),
    ("针灸", ("针灸", "甲乙经", "经穴", "铜人", "针经", "灸法", "明堂")),
    ("本草", ("本草", "药性", "炮炙", "炮制", "药谱", "救荒")),
    ("医经", ("内经", "素问", "灵枢", "难经", "伤寒", "金匮", "温病", "瘟疫", "温热", "湿热")),
    ("诊法", ("脉经", "脉诀", "脉学", "诊家", "舌诊", "舌鉴", "四诊", "望诊", "闻诊")),
    ("专科", ("女科", "妇科", "产科", "儿科", "幼科", "痘疹", "外科", "疡医", "眼科", "喉科", "口齿", "伤科", "骨科")),
    ("方剂", ("方剂", "局方", "验方", "奇方", "良方", "汤头", "千金", "普济", "医方", "方论", "医案", "临证", "医话")),
    ("养生", ("养生", "寿世", "遵生", "摄生", "保生", "颐养")),
]

FIELD_RE = {
    "title": re.compile(r"^\s*书名[：:]\s*(.+?)\s*$"),
    "author": re.compile(r"^\s*作者[：:]\s*(.+?)\s*$"),
    "dynasty": re.compile(r"^\s*朝代[：:]\s*(.+?)\s*$"),
    "year_text": re.compile(r"^\s*年份[：:]\s*(.+?)\s*$"),
}


def decode(raw: bytes) -> str:
    for enc in ("gb18030", "utf-8", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("gb18030", errors="ignore")


def guess_category(title: str) -> str:
    for category, keywords in CATEGORY_RULES:
        if any(k in title for k in keywords):
            return category
    return "综合"


def parse_file(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        text = decode(fh.read())

    meta = {"title": None, "author": None, "dynasty": None, "year_text": None}
    # 元数据只出现在文件开头若干行，扫够即停，避免全文误命中。
    for line in text.splitlines()[:40]:
        for key, pattern in FIELD_RE.items():
            if meta[key]:
                continue
            m = pattern.match(line)
            if m:
                value = m.group(1).strip().rstrip("　 ")
                meta[key] = value or None

    fallback_title = os.path.splitext(os.path.basename(path))[0]
    # 文件名形如 "000-神农本草经"，去掉序号前缀。
    fallback_title = re.sub(r"^\d+[-_\s]*", "", fallback_title).strip()

    title = meta["title"] or fallback_title
    return {
        "title": title[:200],
        "author": (meta["author"] or None),
        "dynasty": (meta["dynasty"] or None),
        "year_text": (meta["year_text"] or None),
        "category": guess_category(title),
        "source_file": os.path.basename(path),
    }


def main() -> int:
    if not os.path.isdir(SRC_DIR):
        print(f"[error] 未找到语料目录: {SRC_DIR}", file=sys.stderr)
        return 1

    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.txt")))
    books = [parse_file(p) for p in files]

    # 按书名去重：同一部书可能有多版本文件。
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for b in books:
        key = b["title"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(unique, fh, ensure_ascii=False, indent=1)

    with_meta = sum(1 for b in unique if b["author"] and b["dynasty"])
    cats: dict[str, int] = {}
    for b in unique:
        cats[b["category"]] = cats.get(b["category"], 0) + 1

    print(f"源文件: {len(files)}  去重后: {len(unique)}")
    print(f"含作者+朝代: {with_meta}")
    print("分类分布:", json.dumps(cats, ensure_ascii=False))
    print(f"输出: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
