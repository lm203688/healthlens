# -*- coding: utf-8 -*-
"""把 data/classical_books.json 转成幂等 SQL，供 psql 直接导入。

幂等靠 ``WHERE NOT EXISTS (title = ...)``，重复执行不会灌重复数据。
字符串用标准 SQL 写法转义单引号，避免书名里的引号破坏语句。
"""
from __future__ import annotations

import json
import os
import sys

SRC = os.path.join("data", "classical_books.json")
OUT = os.path.join("data", "classical_books.sql")

COLS = ("id", "title", "author", "dynasty", "year_text", "category")


def sql_literal(value: str | None) -> str:
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def main() -> int:
    if not os.path.isfile(SRC):
        print(f"[error] 缺少 {SRC}，请先运行 tools/parse_classical_books.py", file=sys.stderr)
        return 1

    with open(SRC, encoding="utf-8") as fh:
        books = json.load(fh)

    lines = [
        "-- 自动生成，请勿手改。来源: tools/gen_books_sql.py",
        "BEGIN;",
    ]
    for b in books:
        title = b.get("title") or ""
        if not title:
            continue
        values = ", ".join(
            [
                "gen_random_uuid()::text",
                sql_literal(title),
                sql_literal(b.get("author")),
                sql_literal(b.get("dynasty")),
                sql_literal(b.get("year_text")),
                sql_literal(b.get("category")),
            ]
        )
        lines.append(
            "INSERT INTO tcm_classical_books (%s) SELECT %s "
            "WHERE NOT EXISTS (SELECT 1 FROM tcm_classical_books WHERE title = %s);"
            % (", ".join(COLS), values, sql_literal(title))
        )
    lines.append("COMMIT;")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"生成 {len(lines) - 3} 条 INSERT -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
