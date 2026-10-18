"""自动生成 alembic 007_add_remaining_models.py。

遍历 app.models.Base.metadata，找出所有 ORM 定义但 alembic/versions/ 里
还没覆盖的表，生成 op.create_table / op.create_index / op.create_unique_constraint
的 Python 代码。downgrade 按 FK 拓扑反序 drop_table。

用法：
    python tools/gen_schema_migration.py --out alembic/versions/007_add_remaining_models.py

不依赖真实数据库连接，纯静态生成。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, Column
from sqlalchemy.schema import UniqueConstraint, Index
from sqlalchemy.sql.type_api import TypeEngine


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _orm_tables() -> MetaData:
    """触发所有 model 定义后返回 Base.metadata。"""
    from app.models import Base  # type: ignore

    return Base.metadata


def _migration_covered() -> set[str]:
    """扫描 alembic/versions/*.py 里已 create_table 的表名。"""
    mig_dir = REPO_ROOT / "alembic" / "versions"
    covered: set[str] = set()
    for path in mig_dir.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"""op\.create_table\(\s*['\"]([^'\"]+)['\"]""", src):
            covered.add(m.group(1))
    return covered


# ---------------------------------------------------------------
# 类型 → Python 源码
# ---------------------------------------------------------------

def _type_to_source(col_type: TypeEngine) -> str:
    """把 SQLAlchemy TypeEngine 转成 sa.XXX(...) 代码字符串。"""
    t = col_type.__class__.__name__
    if t == "String" or t == "VARCHAR":
        length = getattr(col_type, "length", None)
        return f"sa.String({length})" if length else "sa.String"
    if t in ("Text", "TEXT", "LargeBinary"):
        return f"sa.{t}"
    if t in ("Integer", "INT"):
        return "sa.Integer"
    if t in ("BigInteger",):
        return "sa.BigInteger"
    if t in ("SmallInteger",):
        return "sa.SmallInteger"
    if t in ("Float", "REAL", "Double", "NUMERIC", "Numeric"):
        prec = getattr(col_type, "precision", None)
        scale = getattr(col_type, "scale", None)
        if prec is not None:
            return f"sa.Numeric({prec}, {scale or 0})"
        return "sa.Numeric"
    if t == "DateTime":
        tz = getattr(col_type, "timezone", False)
        return f"sa.DateTime(timezone={bool(tz)})"
    if t == "Date":
        return "sa.Date"
    if t == "Boolean":
        return "sa.Boolean"
    if t == "JSON":
        return "sa.JSON"
    if t in ("Enum",):
        members = list(getattr(col_type, "enums", []))
        native_enum = getattr(col_type, "native_enum", True)
        return (
            f"sa.Enum({', '.join(repr(m) for m in members)}, "
            f"native_enum={str(native_enum).lower()})"
        )
    if t in ("UUID",):
        return "sa.String(36)"
    # fallback：字符串名
    return f"sa.{t}"


def _server_default_expr(col: Column) -> str | None:
    """列的 server_default → Python 源码片段。"""
    sd = col.server_default
    if sd is None:
        return None
    text = getattr(sd, "arg", None)
    if text is None:
        text = getattr(sd, "text", None)
    if text is None:
        return None
    # SQLAlchemy 的 DefaultClause.arg 可能是 str / TextClause / callable
    if callable(text):
        text = text()
    if hasattr(text, "text"):
        text = text.text
    text = str(text)
    # sa.func.now() 类表达式
    if "now" in text.lower() or "current_timestamp" in text.lower():
        return "sa.func.now()"
    # 简单字符串/数字字面量
    if text and (text[0] == "'" or text[0] == '"'):
        # 已带引号
        return f"'{text.strip(chr(39))}'" if text.startswith("'") else f"'{text.strip(chr(34))}'"
    return repr(text)


def _fk_source(col: Column, table: Table) -> str | None:
    """列上的外键 → sa.ForeignKey(...) 源码。"""
    for fk in col.foreign_keys:
        target_table = fk.column.table.name
        target_col = fk.column.name
        parts = [f"sa.ForeignKey('{target_table}.{target_col}'"]
        if fk.ondelete:
            parts.append(f"ondelete='{fk.ondelete}'")
        if fk.onupdate:
            parts.append(f"onupdate='{fk.onupdate}'")
        parts.append(")")
        # 位置参数之间用逗号分隔
        return ", ".join(parts[:-1]) + parts[-1]
    return None


def _column_line(col: Column, is_pk: bool, indent: str) -> str:
    """单列 → 'sa.Column(...),' 一行，字段间用逗号+缩进分隔。

    注意：sa.Column(name, type_, *args, **kwargs) 的位置参数是 ForeignKey 等，
    必须放在所有 keyword (nullable/server_default/primary_key) 前面。
    """
    head = f"{indent}sa.Column('{col.name}', {_type_to_source(col.type)}"
    attrs: list[str] = []
    # 位置参数（ForeignKey）先入
    fk = _fk_source(col, col.table)
    if fk:
        attrs.append(fk)
    # 关键字参数
    if is_pk:
        attrs.append("primary_key=True")
    elif col.nullable:
        attrs.append("nullable=True")
    sd = _server_default_expr(col)
    if sd:
        attrs.append(f"server_default={sd}")
    sep = f",\n{indent}    "
    return sep.join([head, *attrs]) + "),"


def _create_table_block(table: Table) -> str:
    """Table → op.create_table(...) 代码块。

    唯一约束内联到 create_table（跨 SQLite/PostgreSQL 都工作），
    避免 op.create_unique_constraint 在 SQLite 上触发 ALTER 不支持。
    """
    cols = list(table.columns)
    pk_cols = {c.name for c in table.primary_key.columns}
    indent = "    "
    lines = [f"    # {table.name}"]
    lines.append(f"    op.create_table('{table.name}',")
    for col in cols:
        is_pk = col.name in pk_cols and len(pk_cols) == 1
        lines.append(_column_line(col, is_pk, indent))
    # 表级唯一约束内联（跨方言通用）
    for con in list(table.constraints):
        if isinstance(con, UniqueConstraint) and len(con.columns) > 1:
            cols_arg = ", ".join(f"'{c.name}'" for c in con.columns)
            name = con.name or f"uq_{table.name}_{'_'.join(c.name for c in con.columns)}"
            lines.append(f"{indent}sa.UniqueConstraint({cols_arg}, name='{name}')")
    lines.append("    )")
    return "\n".join(lines)


def _index_block(index: Index) -> str:
    """Index → op.create_index(...)。"""
    cols = ", ".join(f"'{c}'" for c in index.columns.keys())
    return f"    op.create_index('{index.name}', '{index.table.name}', [{cols}])"


def _unique_constraint_block(table: Table) -> list[str]:
    """表级多列唯一约束的独立调用（保留但不再使用；单列唯一约束走 ORM 自动）。"""
    lines = []
    for con in table.constraints:
        if isinstance(con, UniqueConstraint) and len(con.columns) > 1:
            cols = ", ".join(f"'{c.name}'" for c in con.columns)
            name = con.name or f"uq_{table.name}_{'_'.join(c.name for c in con.columns)}"
            lines.append(
                f"    op.create_unique_constraint('{name}', '{table.name}', [{cols}])"
            )
    return lines


# ---------------------------------------------------------------
# 拓扑排序：让 upgrade 按依赖顺序建表，downgrade 按反序删表
# ---------------------------------------------------------------

def _topo_sort(tables: list[Table]) -> list[Table]:
    """按 FK 依赖拓扑排序。"""
    names = {t.name: t for t in tables}
    visited: set[str] = set()
    order: list[str] = []

    def visit(name: str, path: set[str]):
        if name in visited:
            return
        if name in path:
            return  # 循环依赖，跳过
        t = names.get(name)
        if t is None:
            return
        for fk in t.foreign_keys:
            dep = fk.column.table.name
            if dep in names:
                visit(dep, path | {name})
        visited.add(name)
        order.append(name)

    for t in tables:
        visit(t.name, set())
    return [names[n] for n in order]


# ---------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------

def _find_head_revision() -> str:
    """找 alembic 现有最新 revision ID。"""
    mig_dir = REPO_ROOT / "alembic" / "versions"
    revs: list[tuple[str, str]] = []  # (revision, down_revision)
    for path in mig_dir.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        r = re.search(r"""^revision\s*=\s*['\"]([^'\"]+)['\"]""", src, re.MULTILINE)
        d = re.search(r"""^down_revision\s*=\s*['\"]([^'\"]+)['\"]""", src, re.MULTILINE)
        if r:
            revs.append((r.group(1), d.group(1) if d else ""))
    if not revs:
        return ""
    # 找没被任何 migration 作为 down_revision 引用的那个 = head
    downs = {d for _, d in revs if d}
    heads = [r for r, _ in revs if r not in downs]
    return heads[-1] if heads else revs[-1][0]


def generate(out_path: Path) -> None:
    metadata = _orm_tables()
    covered = _migration_covered()
    all_tables = list(metadata.tables.values())
    missing_tables = [t for t in all_tables if t.name not in covered]

    if not missing_tables:
        print(f"[gen] 无缺失表，跳过生成。{out_path} 未创建。")
        return

    ordered = _topo_sort(missing_tables)
    down_revision = _find_head_revision()

    print(f"[gen] 缺失表 {len(missing_tables)} 张：")
    for t in ordered:
        print(f"  - {t.name}")

    upgrade_body: list[str] = []
    for t in ordered:
        upgrade_body.append(_create_table_block(t))
        for idx in list(t.indexes):
            upgrade_body.append(_index_block(idx))
        upgrade_body.extend(_unique_constraint_block(t))
        upgrade_body.append("")

    # downgrade：反序 drop 索引/表（唯一约束随表一起消失，无需单独 drop_constraint）
    downgrade_body: list[str] = []
    for t in reversed(ordered):
        for idx in list(t.indexes):
            downgrade_body.append(
                f"    op.drop_index('{idx.name}', table_name='{t.name}')"
            )
        downgrade_body.append(f"    op.drop_table('{t.name}')")
        downgrade_body.append("")

    today = date.today().isoformat()
    content = f'''"""补齐 {len(missing_tables)} 张缺失的 ORM 表迁移

Revision ID: 007_add_remaining_models
Revises: {down_revision}
Create Date: {today}

背景：v0.30.0 全新部署 `alembic upgrade head` 后注册即崩
(`no such column: users.is_active`)，根因是 56 张 ORM 表里
{len(missing_tables)} 张没有对应迁移，生产靠 `Base.metadata.create_all`
兜底。本迁移把差异补齐，使纯 alembic 路径可跑通。

生成方式：`python tools/gen_schema_migration.py`。人工复核后合并。
"""
from alembic import op
import sqlalchemy as sa


revision = '007_add_remaining_models'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None


def upgrade() -> None:
{chr(10).join(upgrade_body)}


def downgrade() -> None:
{chr(10).join(downgrade_body)}
'''

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"[gen] 已写入 {out_path}（{out_path.stat().st_size} 字节）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="alembic/versions/007_add_remaining_models.py")
    args = ap.parse_args()
    generate(REPO_ROOT / args.out)
