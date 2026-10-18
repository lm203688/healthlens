"""D0 列级 schema parity：全新空库 alembic upgrade head ↔ ORM 列集合零缺口。

背景（2026-10-18 实证）：
    10-16 报告冒烟枪 ``no such column: users.is_active`` 的根因是**列级**缺口——
    ``tests/test_schema_parity.py`` 只比对表名，007 补齐 32 张表后表名 parity 全绿，
    但 users 表仍缺 6 列（is_active/nickname/referral_code/utm_*），全新部署注册即崩。
    本测试把 parity 从表名级升级到**列级**：空库跑真实 alembic 迁移链，
    再逐表比对 ORM 声明的列集合，任何缺失即 CI 红灯。

与 test_schema_parity.py 的分工：
    - test_schema_parity.py：静态正则扫描（快，无需 DB），防漏建表；
    - 本文件：真实迁移执行 + 列级比对（慢，需 DB），防漏加列——冒烟枪的根因级防线。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect

TESTS_DIR = Path(__file__).resolve().parent  # .../healthlens/tests/lib
REPO_ROOT = TESTS_DIR.parents[1]  # .../healthlens
SCRIPT_LOCATION = REPO_ROOT / "alembic"


# Sync-only env.py（与 test_migration_roundtrip.py 同款：绕开 repo 的 async env.py）
SYNC_ENV_PY = '''\
from alembic import context
from sqlalchemy import create_engine

config = context.config
url = config.get_main_option("sqlalchemy.url")
engine = create_engine(url)
with engine.connect() as conn:
    conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
    conn.commit()
    context.configure(connection=conn)
    with context.begin_transaction():
        context.run_migrations()
    conn.commit()
engine.dispose()
'''


@pytest.fixture(scope="module")
def migrated_engine():
    """全新空库跑完整 alembic 迁移链，返回连接该库的 engine。"""
    tmp_dir = tempfile.mkdtemp(prefix="hl_colparity_")
    try:
        db_fd, db_path = tempfile.mkstemp(suffix=".sqlite", dir=tmp_dir)
        os.close(db_fd)
        db_url = f"sqlite:///{db_path}"

        alembic_dir = Path(tmp_dir) / "alembic"
        alembic_dir.mkdir()
        shutil.copytree(SCRIPT_LOCATION / "versions", alembic_dir / "versions")
        (alembic_dir / "env.py").write_text(SYNC_ENV_PY, encoding="utf-8")

        cfg = AlembicConfig()
        cfg.set_main_option("script_location", str(alembic_dir))
        cfg.set_main_option("sqlalchemy.url", db_url)
        cfg.set_main_option("path_separator", os.pathsep)

        alembic_command.upgrade(cfg, "head")

        engine = create_engine(db_url, future=True)
        yield engine
        engine.dispose()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _orm_metadata():
    """触发全部 model 注册，返回 Base.metadata。"""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from app.models import Base  # noqa: PLC0415
    return Base.metadata


class TestColumnLevelParity:
    """ORM 每张表的每个列都必须由迁移链创建——冒烟枪根因级防线。"""

    def test_no_missing_tables(self, migrated_engine):
        meta = _orm_metadata()
        actual = set(inspect(migrated_engine).get_table_names())
        missing = sorted(set(meta.tables) - actual)
        assert missing == [], (
            f"alembic upgrade head 后仍缺 {len(missing)} 张表：{missing}"
        )

    def test_no_missing_columns(self, migrated_engine):
        """核心断言：ORM 列集合 ⊆ 迁移后实际列集合（逐表）。"""
        meta = _orm_metadata()
        insp = inspect(migrated_engine)
        gaps: dict[str, list[str]] = {}
        for tname in sorted(set(meta.tables) & set(insp.get_table_names())):
            orm_cols = {c.name for c in meta.tables[tname].columns}
            act_cols = {c["name"] for c in insp.get_columns(tname)}
            gap = sorted(orm_cols - act_cols)
            if gap:
                gaps[tname] = gap
        assert gaps == {}, (
            f" alembic 迁移链漏建 {sum(len(v) for v in gaps.values())} 列"
            f"（涉及 {len(gaps)} 张表）：\n"
            + "\n".join(f"  {t}: {cols}" for t, cols in gaps.items())
            + "\n\n这正是 10-16 冒烟枪 no such column: users.is_active 的根因形态。"
            "修复：新建 alembic 迁移 op.add_column 补齐（参考 009_users_missing_columns）。"
        )

    def test_no_extra_columns(self, migrated_engine):
        """迁移不应创建 ORM 不知道的列（防手写迁移漂移）。alembic_version 除外。"""
        meta = _orm_metadata()
        insp = inspect(migrated_engine)
        extras: dict[str, list[str]] = {}
        for tname in sorted(set(meta.tables) & set(insp.get_table_names())):
            orm_cols = {c.name for c in meta.tables[tname].columns}
            act_cols = {c["name"] for c in insp.get_columns(tname)}
            extra = sorted(act_cols - orm_cols)
            if extra:
                extras[tname] = extra
        assert extras == {}, (
            f"迁移创建的列不在 ORM 中（ORM/迁移漂移）：\n"
            + "\n".join(f"  {t}: {cols}" for t, cols in extras.items())
        )

    def test_registered_smoke_columns_present(self, migrated_engine):
        """冒烟枪回归锚点：注册链路直接依赖的 users 列必须存在。"""
        insp = inspect(migrated_engine)
        cols = {c["name"] for c in insp.get_columns("users")}
        for required in ("is_active", "email", "password_hash", "role"):
            assert required in cols, f"users.{required} 缺失——注册链路会崩"

    def test_federated_prework_columns_present(self, migrated_engine):
        """D4 联邦预埋：乐观锁列 + 唯一索引在真实迁移后存在。"""
        insp = inspect(migrated_engine)
        for tname in ("axis_snapshots", "biomarker_readings"):
            cols = {c["name"] for c in insp.get_columns(tname)}
            assert "version_id" in cols, f"{tname}.version_id 缺失（D4 乐观锁）"
        idx_names = {
            i["name"] for i in insp.get_indexes("axis_snapshots") if i.get("unique")
        }
        idx_names |= {
            i["name"] for i in insp.get_indexes("biomarker_readings") if i.get("unique")
        }
        assert "uq_snapshots_study_date_source" in idx_names
        assert "uq_readings_study_ts_loinc" in idx_names
