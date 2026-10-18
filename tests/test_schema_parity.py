"""D0 Schema parity 测试。

背景：v0.30.0 全新部署走 ``alembic upgrade head`` 后注册即崩
（``no such column: users.is_active``），根因是 56 张 ORM 表里 32 张没有
对应的 alembic 迁移，生产环境只能靠 ``Base.metadata.create_all`` 补上，
一旦有人跑纯 alembic 路径就直接崩。

本测试锁死 ORM ↔ migration 的差集必须为空，任何漏掉的表都会让 CI 直接红灯。
"""

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_DIR = REPO_ROOT / "alembic" / "versions"


def _orm_tables() -> set[str]:
    """触发所有 model 定义后从 Base.metadata 读表名。"""
    # 显式导入 app.models 以触发 __init__.py 里的 model 注册
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from app.models import Base  # type: ignore

    return set(Base.metadata.tables.keys())


def _migration_covered_tables() -> set[str]:
    """扫描所有 alembic 迁移文件，提取被 create_table / sa.table 引用的表名。"""
    covered: set[str] = set()
    for path in ALEMBIC_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        # sa.table('xxx') 或 sa.table("xxx")
        for m in re.finditer(r"""sa\.table\(['\"]([^'\"]+)['\"]""", src):
            covered.add(m.group(1))
        # op.create_table('xxx', ...) 或 op.create_table("xxx", ...)
        for m in re.finditer(r"""op\.create_table\(\s*['\"]([^'\"]+)['\"]""", src):
            covered.add(m.group(1))
        # op.drop_table 也算"处理过"（downgrade 引用它）
        for m in re.finditer(r"""op\.drop_table\(\s*['\"]([^'\"]+)['\"]""", src):
            covered.add(m.group(1))
    return covered


@pytest.fixture(scope="module")
def diff() -> tuple[set[str], set[str], set[str]]:
    orm = _orm_tables()
    mig = _migration_covered_tables()
    return orm, mig, sorted(orm - mig)


class TestSchemaParity:
    """ORM 表必须在迁移里可追溯——否则全新部署会崩。"""

    def test_no_missing_migrations(self, diff: tuple[set[str], set[str], set[str]]):
        orm, mig, missing = diff
        assert missing == [], (
            f"以下 {len(missing)} 张 ORM 表在 alembic/versions/ 里没有对应迁移：\n"
            + "\n".join(f"  - {t}" for t in missing)
            + "\n\n全新部署 alembic upgrade head 后这些表不存在，业务代码一跑就崩。\n"
            "  修复：alembic revision -m 'add missing tables' --autogenerate\n"
            "  然后人工复核生成的 DDL。"
        )

    def test_orm_tables_count_reasonable(self, diff: tuple[set[str], set[str], set[str]]):
        """ORM 表数量应有一个下界，防止未来有人误删模型而不修迁移。"""
        orm, _, _ = diff
        assert len(orm) >= 30, f"ORM 表数异常偏少：{len(orm)}（预期 ≥ 30）"

    def test_migrations_reference_known_tables(self, diff: tuple[set[str], set[str], set[str]]):
        """迁移里引用的表不应凭空存在——防止有人手写错表名。"""
        orm, mig, _ = diff
        unknown = sorted(mig - orm)
        # alembic_version 是 alembic 自动维护的版本表，允许
        allowed_meta = {"alembic_version"}
        unknown = [t for t in unknown if t not in allowed_meta]
        assert unknown == [], (
            f"以下 {len(unknown)} 张迁移引用的表在 ORM 里不存在：\n"
            + "\n".join(f"  - {t}" for t in unknown)
        )

    def test_alembic_versions_dir_exists(self):
        assert ALEMBIC_DIR.exists(), f"alembic/versions 目录缺失：{ALEMBIC_DIR}"
        assert (ALEMBIC_DIR / ".gitkeep").exists(), "alembic/versions/.gitkeep 缺失"

    def test_all_migration_files_parse(self):
        """所有迁移文件必须是合法 Python（防止生成过程留语法错误）。"""
        import ast

        failures = []
        for path in ALEMBIC_DIR.glob("*.py"):
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as e:
                failures.append(f"{path.name}: {e}")
        assert failures == [], (
            "以下迁移文件存在语法错误：\n" + "\n".join(failures)
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
