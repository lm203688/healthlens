"""D4 联邦预埋迁移往返测试（2026-10-17）。

覆盖：
- 008_federated_optimistic_lock 迁移的 upgrade/downgrade 往返一致性
- axis_snapshots.version_id 乐观锁字段存在
- axis_snapshots 唯一约束 (study_id, date, source) 存在
- biomarker_readings.version_id 乐观锁字段存在
- biomarker_readings 唯一约束 (study_id, sampled_at, loinc_code) 存在
- downgrade 后这些字段与约束消失
- 重复 upgrade 后再次出现
"""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text


ALEMBIC_DIR = os.path.join(os.path.dirname(__file__), "..", "alembic")
ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


@pytest.fixture(scope="module")
def tmp_db_path():
    """临时 SQLite 文件路径（跨用例共享）。"""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="hl_fed_")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def _build_config(tmp_db_path: str):
    """构造 Alembic Config，指向临时库（用 aiosqlite 匹配 env.py 的异步驱动）。"""
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_db_path}")
    return cfg


def _run(cfg, command_name, *args):
    """调用 alembic command module（避开 `from alembic import command` 时的模块名冲突）。"""
    from alembic import command as _alembic_command_module
    getattr(_alembic_command_module, command_name)(cfg, *args)


def test_upgrade_apply_all_success(tmp_db_path):
    """从空库 upgrade head，全部迁移应成功应用。"""
    cfg = _build_config(tmp_db_path)
    _run(cfg, "upgrade", "head")


def test_after_upgrade_optimistic_lock_columns_exist(tmp_db_path):
    """upgrade head 后 version_id 列应存在。"""
    cfg = _build_config(tmp_db_path)
    _run(cfg, "upgrade", "head")

    engine = create_engine(f"sqlite:///{tmp_db_path}")
    insp = inspect(engine)

    snap_cols = {c["name"] for c in insp.get_columns("axis_snapshots")}
    read_cols = {c["name"] for c in insp.get_columns("biomarker_readings")}

    assert "version_id" in snap_cols, "axis_snapshots.version_id 缺失"
    assert "version_id" in read_cols, "biomarker_readings.version_id 缺失"

    # 唯一约束（SQLite 用索引承载，不返回 constraint；检查索引名）
    snap_idx = [i["name"] for i in insp.get_indexes("axis_snapshots") if i.get("unique")]
    read_idx = [i["name"] for i in insp.get_indexes("biomarker_readings") if i.get("unique")]
    assert "uq_snapshots_study_date_source" in snap_idx, (
        "axis_snapshots 唯一索引缺失"
    )
    assert "uq_readings_study_ts_loinc" in read_idx, (
        "biomarker_readings 唯一索引缺失"
    )

    engine.dispose()


def test_downgrade_then_upgrade_roundtrip(tmp_db_path):
    """downgrade 后字段消失；重新 upgrade 后字段回归。"""
    cfg = _build_config(tmp_db_path)
    _run(cfg, "upgrade", "head")
    engine = create_engine(f"sqlite:///{tmp_db_path}")
    insp = inspect(engine)
    assert "version_id" in {c["name"] for c in insp.get_columns("axis_snapshots")}
    engine.dispose()

    # downgrade 到 008 的父迁移 007（显式目标版本：head 之后新增 009/010 时
    # `-1` 只会退一步到 009，测不到 008 的 downgrade；显式 revision 语义稳定）
    _run(cfg, "downgrade", "007_add_remaining_models")
    engine = create_engine(f"sqlite:///{tmp_db_path}")
    insp = inspect(engine)
    snap_cols = {c["name"] for c in insp.get_columns("axis_snapshots")}
    read_cols = {c["name"] for c in insp.get_columns("biomarker_readings")}
    assert "version_id" not in snap_cols, "downgrade 未移除 axis_snapshots.version_id"
    assert "version_id" not in read_cols, "downgrade 未移除 biomarker_readings.version_id"

    snap_uniques = [u for u in insp.get_unique_constraints("axis_snapshots")
                    if "uq_snapshots_study_date_source" in (u.get("name") or "")]
    read_uniques = [u for u in insp.get_unique_constraints("biomarker_readings")
                    if "uq_readings_study_ts_loinc" in (u.get("name") or "")]
    assert not snap_uniques, "downgrade 未移除 axis_snapshots 唯一约束"
    assert not read_uniques, "downgrade 未移除 biomarker_readings 唯一约束"
    engine.dispose()

    # 再 upgrade 回去
    _run(cfg, "upgrade", "head")
    engine = create_engine(f"sqlite:///{tmp_db_path}")
    insp = inspect(engine)
    assert "version_id" in {c["name"] for c in insp.get_columns("axis_snapshots")}
    assert "version_id" in {c["name"] for c in insp.get_columns("biomarker_readings")}
    engine.dispose()


def test_optimistic_lock_prevents_stale_write(tmp_db_path):
    """乐观锁：CAS 更新遇到 version_id 不匹配应写入 0 行（不双算）。"""
    cfg = _build_config(tmp_db_path)
    _run(cfg, "upgrade", "head")

    engine = create_engine(f"sqlite:///{tmp_db_path}")
    with engine.begin() as conn:
        # 需要 users + studies 才能插快照，先造最小依赖
        conn.execute(text("INSERT INTO users (id, email, password_hash) VALUES ('u1','u1@x','x')"))
        conn.execute(text(
            "INSERT INTO longitudinal_studies (id, user_id, name) VALUES ('s1','u1','n1')"
        ))
        # 插快照 v1
        conn.execute(text(
            "INSERT INTO axis_snapshots (id, study_id, user_id, captured_at, date, jurisdiction, "
            "source, version_id) VALUES ('snap1','s1','u1','2026-10-17','2026-10-17','cn','manual',1)"
        ))
        # 尝试以 v2 覆盖——不匹配，应影响 0 行
        result = conn.execute(text(
            "UPDATE axis_snapshots SET version_id = 3 "
            "WHERE id = 'snap1' AND version_id = 2"
        ))
        assert result.rowcount == 0, "CAS 失败时应 0 行更新，避免 stale write"
        # 用正确 v1 更新到 v2
        result2 = conn.execute(text(
            "UPDATE axis_snapshots SET version_id = 2 "
            "WHERE id = 'snap1' AND version_id = 1"
        ))
        assert result2.rowcount == 1
    engine.dispose()


def test_unique_constraint_rejects_duplicate_study_date_source(tmp_db_path):
    """唯一约束：同一 study + date + source 不可重复插入（防联邦双算）。"""
    cfg = _build_config(tmp_db_path)
    _run(cfg, "upgrade", "head")

    engine = create_engine(f"sqlite:///{tmp_db_path}")
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, password_hash) VALUES ('u2','u2@x','x')"))
        conn.execute(text(
            "INSERT INTO longitudinal_studies (id, user_id, name) VALUES ('s2','u2','n2')"
        ))
        conn.execute(text(
            "INSERT INTO axis_snapshots (id, study_id, user_id, captured_at, date, jurisdiction, "
            "source, version_id) VALUES ('snapA','s2','u2','2026-10-17','2026-10-17','cn','manual',1)"
        ))
        with pytest.raises(IntegrityError) as ei:
            conn.execute(text(
                "INSERT INTO axis_snapshots (id, study_id, user_id, captured_at, date, jurisdiction, "
                "source, version_id) VALUES ('snapB','s2','u2','2026-10-17','2026-10-17','cn','manual',1)"
            ))
        # SQLite 报 UNIQUE constraint failed: axis_snapshots
        assert "UNIQUE" in str(ei.value).upper() or "unique" in str(ei.value).lower()
    engine.dispose()
