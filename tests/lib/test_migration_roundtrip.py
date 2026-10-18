"""D4 联邦预埋迁移 downgrade 往返测试（test_migration_roundtrip.py）

背景（10-16 全面评估报告 D4 / 10-17 科学评估 §四 B 组）：
    alembic/versions/008_federated_optimistic_lock.py 引入了 version_id 乐观锁
    和唯一索引，用于防止联邦学习场景下"最后写入胜"和重复计入导致的静默数据丢失。
    迁移文件的 downgrade 必须严格可逆，否则一旦回滚，axis_snapshots 与
    biomarker_readings 表的 schema 会与 ORM 声明永久漂移，生产库进入
    "既无法向前兼容也无法向后兼容"的悬空状态。

验收（对齐任务 #320）：
    1. upgrade head 后两个表都有 version_id 列 + 唯一索引
    2. downgrade -1 后所有新列与新索引干净删除，不残留任何字段
    3. 再 upgrade head 与首次 upgrade 后 schema 完全一致（幂等往返）
    4. downgrade 不删表（联邦数据属于生产资产，任何降级都不可 delete）
    5. downgrade → upgrade 后 version_id 回到 server_default='1'

设计：
    - 用 tempfile 创建文件级 SQLite DB（in-memory sqlite:// 是 per-connection，
      跨 engine 不共享；file-based 让 env.py engine 与测试 engine 连接同一 DB）
    - 用 tempfile 创建临时 alembic 目录，内含 sync-only env.py + 复制的 versions/
    - 绕开 repo 的 async env.py（其 async_engine_from_config 在 sync sqlite:// 上炸）
    - alembic.command.upgrade / downgrade 通过临时 env.py 执行，测试 engine 做断言

跑法：
    pytest tests/lib/test_migration_roundtrip.py -v
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect


# ---------------------------------------------------------------------------
# 路径探测
# ---------------------------------------------------------------------------

TESTS_DIR = Path(__file__).resolve().parent  # .../healthlens/tests/lib
REPO_ROOT = TESTS_DIR.parents[1]  # .../healthlens
SCRIPT_LOCATION = REPO_ROOT / "alembic"


# ---------------------------------------------------------------------------
# Sync-only env.py（绕过 repo 的 async env.py）
# ---------------------------------------------------------------------------

SYNC_ENV_PY = '''\
from alembic import context
from sqlalchemy import create_engine

config = context.config
url = config.get_main_option("sqlalchemy.url")

# PRAGMA foreign_keys=OFF 在迁移过程中允许先建表后加 FK 列，
# 避免迁移链中段因外键目标表未建而失败。
# 关键：PRAGMA 设置后必须 commit 以结束隐式事务，否则后续
# context.begin_transaction() 创建的 SAVEPOINT 在 engine.connect()
# 退出时会被外层隐式事务回滚，导致所有迁移变更丢失。
engine = create_engine(url)
with engine.connect() as conn:
    conn.exec_driver_sql("PRAGMA foreign_keys = OFF")
    conn.commit()  # 提交 PRAGMA 设置（连接级，非事务性）
    context.configure(connection=conn)
    with context.begin_transaction():
        context.run_migrations()
    conn.commit()  # 提交迁移事务
engine.dispose()
'''


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_and_config():
    """创建临时文件 DB + 临时 alembic 目录（含 sync env.py + 复制的 versions/）。

    每个测试独占一个 fresh 环境，隔离 upgrade/downgrade 副作用。
    """
    # 文件级 SQLite（跨 engine 共享同一 DB）
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    import os
    os.close(db_fd)
    db_url = f"sqlite:///{db_path}"

    # 临时 alembic 目录
    tmp_dir = tempfile.TemporaryDirectory()
    alembic_dir = Path(tmp_dir.name) / "alembic"
    alembic_dir.mkdir()

    # 复制 versions/
    shutil.copytree(SCRIPT_LOCATION / "versions", alembic_dir / "versions")

    # 写 sync env.py
    (alembic_dir / "env.py").write_text(SYNC_ENV_PY, encoding="utf-8")

    # 测试用的 verification engine（future=True 适配 SQLAlchemy 2.x）
    engine = create_engine(db_url, future=True)

    # alembic config
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(alembic_dir))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("path_separator", os.pathsep)

    yield engine, cfg, db_url

    engine.dispose()
    tmp_dir.cleanup()
    try:
        os.remove(db_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Schema 检查助手
# ---------------------------------------------------------------------------

def _tables_with_columns(engine_or_conn) -> dict:
    """返回 {table_name: set(columns)}，便于断言 schema。"""
    insp = inspect(engine_or_conn)
    return {t: {c["name"] for c in insp.get_columns(t)}
            for t in insp.get_table_names()}


def _unique_index_columns(engine_or_conn) -> dict:
    """返回 {index_name: {table, columns}}，仅唯一索引。"""
    insp = inspect(engine_or_conn)
    result = {}
    for tbl in insp.get_table_names():
        for idx in insp.get_indexes(tbl):
            if idx.get("unique"):
                result[idx["name"]] = {
                    "table": tbl,
                    "columns": list(idx["column_names"]),
                }
    return result


# ---------------------------------------------------------------------------
# 测试主体
# ---------------------------------------------------------------------------

def test_upgrade_head_adds_version_id_and_unique_indexes(db_and_config):
    """1. upgrade head 后 axis_snapshots + biomarker_readings 都有 version_id + 唯一索引。"""
    engine, cfg, _ = db_and_config

    alembic_command.upgrade(cfg, "head")

    meta = _tables_with_columns(engine)
    assert "version_id" in meta.get("axis_snapshots", set()), (
        f"axis_snapshots 缺少 version_id 列，得到: {sorted(meta.get('axis_snapshots', []))}"
    )
    assert "version_id" in meta.get("biomarker_readings", set()), (
        f"biomarker_readings 缺少 version_id 列，得到: {sorted(meta.get('biomarker_readings', []))}"
    )

    uq = _unique_index_columns(engine)
    assert "uq_snapshots_study_date_source" in uq, (
        f"缺少 uq_snapshots_study_date_source，实际索引: {sorted(uq)}"
    )
    assert "uq_readings_study_ts_loinc" in uq, (
        f"缺少 uq_readings_study_ts_loinc，实际索引: {sorted(uq)}"
    )
    assert uq["uq_snapshots_study_date_source"]["columns"] == [
        "study_id", "date", "source"
    ]
    assert uq["uq_readings_study_ts_loinc"]["columns"] == [
        "study_id", "sampled_at", "loinc_code"
    ]


def test_downgrade_then_upgrade_roundtrip_idempotent(db_and_config):
    """2+3. upgrade → downgrade → upgrade 后 schema 完全一致（幂等往返）。"""
    engine, cfg, _ = db_and_config

    # 1) 到 head
    alembic_command.upgrade(cfg, "head")
    meta_head_1 = _tables_with_columns(engine)
    uq_head_1 = _unique_index_columns(engine)

    # 2) 降到 007（008 的父迁移）
    alembic_command.downgrade(cfg, "007_add_remaining_models")
    meta_down = _tables_with_columns(engine)
    uq_down = _unique_index_columns(engine)

    # 断言 008 引入的东西全部消失
    assert "version_id" not in meta_down.get("axis_snapshots", set()), (
        "downgrade 后 axis_snapshots 仍残留 version_id"
    )
    assert "version_id" not in meta_down.get("biomarker_readings", set()), (
        "downgrade 后 biomarker_readings 仍残留 version_id"
    )
    assert "uq_snapshots_study_date_source" not in uq_down, (
        "downgrade 后 uq_snapshots_study_date_source 仍残留"
    )
    assert "uq_readings_study_ts_loinc" not in uq_down, (
        "downgrade 后 uq_readings_study_ts_loinc 仍残留"
    )

    # 3) 再升到 head
    alembic_command.upgrade(cfg, "head")
    meta_head_2 = _tables_with_columns(engine)
    uq_head_2 = _unique_index_columns(engine)

    # 幂等：两次 head 的 schema 完全一致
    assert meta_head_1 == meta_head_2, (
        "upgrade→downgrade→upgrade 后表列集合不一致（不幂等）"
    )
    assert uq_head_1 == uq_head_2, (
        "upgrade→downgrade→upgrade 后唯一索引集合不一致（不幂等）"
    )


def test_downgrade_does_not_drop_federated_tables(db_and_config):
    """4. downgrade 不删表——联邦数据属于生产资产，任何降级都不可 delete。"""
    engine, cfg, _ = db_and_config

    alembic_command.upgrade(cfg, "head")

    # 插入一条真实数据，确认降级不 delete 行
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "INSERT INTO axis_snapshots "
            "(id, study_id, user_id, date, captured_at, axis_scores, version_id) "
            "VALUES ('snap-1', 'study-1', 'user-1', '2026-10-17', "
            "'2026-10-17 09:00:00', '{\"A\": 80}', 1)"
        )
        conn.commit()

    alembic_command.downgrade(cfg, "007_add_remaining_models")

    # 降级后 axis_snapshots 表仍然存在（虽然 version_id 列被删除）
    meta = _tables_with_columns(engine)
    assert "axis_snapshots" in meta, (
        "downgrade 不应删除 axis_snapshots 表"
    )
    assert "biomarker_readings" in meta, (
        "downgrade 不应删除 biomarker_readings 表"
    )

    # 数据行仍在
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT id FROM axis_snapshots WHERE id = 'snap-1'"
        ).fetchall()
        assert len(rows) == 1, "downgrade 不应删除已有数据行"


def test_downgrade_then_upgrade_restores_default_version_id(db_and_config):
    """5. downgrade 后再 upgrade 时，version_id 恢复 server_default='1'（历史行不破坏）。"""
    engine, cfg, _ = db_and_config

    alembic_command.upgrade(cfg, "head")

    # 插入多行，覆盖 version_id 各种值
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "INSERT INTO axis_snapshots "
            "(id, study_id, user_id, date, captured_at, axis_scores, version_id) "
            "VALUES "
            "('snap-a', 'study-1', 'user-1', '2026-10-17', '2026-10-17 09:00:00', '{}', 1), "
            "('snap-b', 'study-1', 'user-1', '2026-10-18', '2026-10-18 09:00:00', '{}', 3)"
        )
        conn.commit()

    # 降级 → 升级
    alembic_command.downgrade(cfg, "007_add_remaining_models")
    alembic_command.upgrade(cfg, "head")

    # version_id 列应回到 server_default='1'（downgrade 删列 + upgrade 重建列）
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT id, version_id FROM axis_snapshots ORDER BY id"
        ).fetchall()
    assert len(rows) == 2, f"应有 2 行数据，实际 {len(rows)}"
    for row_id, version in rows:
        assert version is not None, (
            f"version_id 不应为 NULL（row={row_id}）"
        )
        assert version == 1, (
            f"version_id 应回到 server_default=1（row={row_id}），实际 {version}"
        )


def test_downgrade_is_reversible_across_full_chain(db_and_config):
    """6. 从 head 逐级 downgrade 到 007 → 006 → ... → base 不报错（全链可逆）。"""
    _engine, cfg, _ = db_and_config

    # 逐级降级：010 → 009 → 008 → 007 → 006 → 005 → 004 → 003 → 002 → 001 → base
    chain = [
        "009_users_missing_columns",
        "008_federated_optimistic_lock",
        "007_add_remaining_models",
        "006_add_region_jurisdiction",
        "005_add_gdpr_consent",
        "004_add_checkin_and_audit",
        "003_add_totp_columns",
        "002_add_missing_tables",
        "001_initial",
    ]
    # 先升到 head
    alembic_command.upgrade(cfg, "head")

    # 逐级降级，每一步都不应报错
    for rev in chain:
        alembic_command.downgrade(cfg, rev)

    # 最终降到 base（无迁移）
    alembic_command.downgrade(cfg, "base")

    # 从 base 逐级升回 head，验证可逆
    for rev in reversed(chain):
        alembic_command.upgrade(cfg, rev)

    # 最终升到 head
    alembic_command.upgrade(cfg, "head")

    # 验证 schema 完整
    meta = _tables_with_columns(_engine)
    assert "version_id" in meta["axis_snapshots"], "最终应回到 head schema"
    assert "version_id" in meta["biomarker_readings"], "最终应回到 head schema"


# ---------------------------------------------------------------------------
# 元级断言：迁移文件静态检查
# ---------------------------------------------------------------------------

def test_008_migration_file_declares_both_directions():
    """静态检查 008 迁移文件：upgrade + downgrade 都显式定义，且对称操作 4 个 DDL 语句。"""
    m = SCRIPT_LOCATION / "versions" / "008_federated_optimistic_lock.py"
    assert m.exists(), f"008 迁移文件不存在: {m}"
    content = m.read_text(encoding="utf-8")
    # upgrade 必须包含 4 个 op. 调用（2 add_column + 2 create_index）
    assert content.count("op.add_column") == 2, "upgrade 应 add_column × 2（两个表）"
    assert content.count("op.create_index") == 2, "upgrade 应 create_index × 2（两个表）"
    # downgrade 必须对称
    assert content.count("op.drop_index") == 2, "downgrade 应 drop_index × 2"
    assert content.count("op.drop_column") == 2, "downgrade 应 drop_column × 2"
    # downgrade 必须严格反向（先 drop_index，再 drop_column）——避免依赖失败
    idx_pos = content.index("op.drop_index")
    col_pos = content.index("op.drop_column")
    assert idx_pos < col_pos, (
        "downgrade 应先 drop_index 再 drop_column（顺序反转，避免依赖失败）"
    )
    # revision 链正确
    assert "revision = '008_federated_optimistic_lock'" in content
    assert "down_revision = '007_add_remaining_models'" in content
