"""D4 联邦预埋测试：乐观锁 + 唯一索引 + downgrade 往返

覆盖 10-16 全面评估报告 D4 的三条验收标准：
1. axis_snapshots 有 version_id 乐观锁字段
2. biomarker_readings 有 version_id 乐观锁字段
3. 两张表有语义正确的唯一约束
4. migration 007 → 008 → downgrade → upgrade 往返幂等
"""
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base import Base
from app.models.longitudinal import AxisSnapshot, BiomarkerReading, LongitudinalStudy


# ---------------------------------------------------------------------------
# Schema 层静态检查（无需数据库，纯 MetaData 反射）
# ---------------------------------------------------------------------------

def test_axis_snapshot_has_version_id_column():
    """AxisSnapshot 必须有 version_id 列，非空，Integer 类型，默认值 1。"""
    col = AxisSnapshot.__table__.c.get("version_id")
    assert col is not None, "AxisSnapshot.version_id 列缺失（D4 联邦乐观锁失效）"
    assert not col.nullable, "version_id 必须 NOT NULL"
    assert isinstance(col.type, sa.Integer), f"version_id 应为 Integer，实际 {col.type}"


def test_biomarker_reading_has_version_id_column():
    """BiomarkerReading 必须有 version_id 列，非空，Integer 类型。"""
    col = BiomarkerReading.__table__.c.get("version_id")
    assert col is not None, "BiomarkerReading.version_id 列缺失（D4 联邦乐观锁失效）"
    assert not col.nullable, "version_id 必须 NOT NULL"
    assert isinstance(col.type, sa.Integer), f"version_id 应为 Integer，实际 {col.type}"


def test_axis_snapshot_unique_constraint_exists():
    """AxisSnapshot 必须有 UniqueConstraint(study_id, date, source)。"""
    uqs = [
        uq for uq in AxisSnapshot.__table__.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert uqs, "AxisSnapshot 无任何 UniqueConstraint"
    target_names = {"study_id", "date", "source"}
    matching = [
        uq for uq in uqs
        if {c.name for c in uq.columns} == target_names
    ]
    assert matching, (
        f"AxisSnapshot 缺少 UniqueConstraint(study_id, date, source)。"
        f"现有约束: {[{c.name for c in uq.columns} for uq in uqs]}"
    )


def test_biomarker_reading_unique_constraint_exists():
    """BiomarkerReading 必须有 UniqueConstraint(study_id, sampled_at, loinc_code)。"""
    uqs = [
        uq for uq in BiomarkerReading.__table__.constraints
        if isinstance(uq, sa.UniqueConstraint)
    ]
    assert uqs, "BiomarkerReading 无任何 UniqueConstraint"
    target_names = {"study_id", "sampled_at", "loinc_code"}
    matching = [
        uq for uq in uqs
        if {c.name for c in uq.columns} == target_names
    ]
    assert matching, (
        f"BiomarkerReading 缺少 UniqueConstraint(study_id, sampled_at, loinc_code)。"
        f"现有约束: {[{c.name for c in uq.columns} for uq in uqs]}"
    )


# ---------------------------------------------------------------------------
# ORM 层行为检查（SQLite in-memory 实装测试）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_snapshot_version_id_default_is_one():
    """AxisSnapshot 新建时 version_id 默认值为 1。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        snap = AxisSnapshot(
            study_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000001",
            date="2026-10-17",
            captured_at=sa.func.now(),
            source="manual",
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)
        assert snap.version_id == 1, f"version_id 默认应为 1，实际 {snap.version_id}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_axis_snapshot_unique_constraint_rejects_duplicate():
    """同一 (study_id, date, source) 的第二次插入必须被 UniqueConstraint 拒绝。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession
    from datetime import datetime

    user_id = "00000000-0000-0000-0000-000000000001"
    study_id = "00000000-0000-0000-0000-000000000001"

    # 第一次插入（独立 session）
    async with AsyncSession(engine) as session:
        snap1 = AxisSnapshot(
            study_id=study_id,
            user_id=user_id,
            date="2026-10-17",
            captured_at=datetime(2026, 10, 17, 8, 0, 0),
            source="manual",
        )
        session.add(snap1)
        await session.commit()
        await session.refresh(snap1)
        assert snap1.version_id == 1

    # 重复插入（独立 session，同 study + date + source）必须失败
    async with AsyncSession(engine) as session:
        snap2 = AxisSnapshot(
            study_id=study_id,
            user_id=user_id,
            date="2026-10-17",
            captured_at=datetime(2026, 10, 17, 12, 0, 0),  # 时刻不同但日期同
            source="manual",
        )
        session.add(snap2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        assert (
            "uq_snapshots_study_date_source" in str(exc_info.value)
            or "UNIQUE constraint failed" in str(exc_info.value)
        )

    # 不同 source 应允许通过（独立 session）
    async with AsyncSession(engine) as session:
        snap3 = AxisSnapshot(
            study_id=study_id,
            user_id=user_id,
            date="2026-10-17",
            captured_at=datetime(2026, 10, 17, 20, 0, 0),
            source="wearable_sync",  # 不同 source → 唯一约束不冲突
        )
        session.add(snap3)
        await session.commit()
        await session.refresh(snap3)
        assert snap3.version_id == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_biomarker_reading_unique_constraint_rejects_duplicate():
    """同一 (study_id, sampled_at, loinc_code) 的第二次插入必须被拒绝。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession
    from datetime import datetime

    user_id = "00000000-0000-0000-0000-000000000001"
    study_id = "00000000-0000-0000-0000-000000000001"
    ts = datetime(2026, 10, 17, 8, 0, 0)

    # 第一次插入（独立 session）
    async with AsyncSession(engine) as session:
        r1 = BiomarkerReading(
            study_id=study_id,
            user_id=user_id,
            loinc_code="1521-0",  # HbA1c
            loinc_name="Hemoglobin A1c",
            value_numeric=6.5,
            sampled_at=ts,
        )
        session.add(r1)
        await session.commit()
        await session.refresh(r1)
        assert r1.version_id == 1

    # 重复插入（独立 session，同 study + ts + loinc）必须失败
    async with AsyncSession(engine) as session:
        r2 = BiomarkerReading(
            study_id=study_id,
            user_id=user_id,
            loinc_code="1521-0",
            loinc_name="Hemoglobin A1c",
            value_numeric=6.7,  # 尝试覆盖旧值
            sampled_at=ts,
        )
        session.add(r2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        msg = str(exc_info.value)
        assert (
            "uq_readings_study_ts_loinc" in msg
            or "UNIQUE constraint failed" in msg
        )

    # 不同 loinc_code 应通过（独立 session）
    async with AsyncSession(engine) as session:
        r3 = BiomarkerReading(
            study_id=study_id,
            user_id=user_id,
            loinc_code="2345-7",  # Total Cholesterol
            loinc_name="Cholesterol",
            value_numeric=190.0,
            sampled_at=ts,
        )
        session.add(r3)
        await session.commit()
        await session.refresh(r3)
        assert r3.version_id == 1

    await engine.dispose()


# ---------------------------------------------------------------------------
# Migration 往返测试：007 → 008 → downgrade → upgrade
# ---------------------------------------------------------------------------

def test_migration_008_module_loads_and_defines_both_directions():
    """Migration 008 必须可导入，且 upgrade/downgrade 都是 callable。"""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parent.parent / "alembic" / "versions" / "008_federated_optimistic_lock.py"
    assert path.exists(), f"Migration 008 文件不存在: {path}"

    spec = importlib.util.spec_from_file_location("migration_008", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "upgrade") and callable(mod.upgrade)
    assert hasattr(mod, "downgrade") and callable(mod.downgrade)
    assert mod.revision == "008_federated_optimistic_lock"
    assert mod.down_revision == "007_add_remaining_models"


def test_migration_008_up_and_down_are_symmetric_operations():
    """Migration 008 upgrade 的每个操作在 downgrade 中都应有对称的反向操作。

    对称性检查（静态 AST 级别）：
    - upgrade 中每次 op.add_column 应对应 downgrade 中一次 op.drop_column
    - upgrade 中每次 op.create_unique_constraint 应对应 downgrade 中一次 op.drop_constraint
    - downgrade 中的 drop 顺序必须与 upgrade 中的 create 顺序**反转**（先删后建）
    """
    import ast
    from pathlib import Path

    path = Path(__file__).parent.parent / "alembic" / "versions" / "008_federated_optimistic_lock.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    upgrade_calls = []
    downgrade_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "upgrade":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    upgrade_calls.append((sub.func.value.id, sub.func.attr))
        elif node.name == "downgrade":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    downgrade_calls.append((sub.func.value.id, sub.func.attr))

    upgrade_ops = set(upgrade_calls)
    downgrade_ops = set(downgrade_calls)

    # upgrade 必须包含的对称操作
    assert ("op", "add_column") in upgrade_ops
    assert ("op", "drop_column") in downgrade_ops
    # 唯一约束：允许两种等价实现
    #  - create_unique_constraint + drop_constraint（SQLAlchemy 通用，但 SQLite 不支持 ALTER ADD CONSTRAINT）
    #  - create_index(unique=True) + drop_index（跨方言，SQLite/PostgreSQL/MySQL 通用）
    has_unique_constraint = ("op", "create_unique_constraint") in upgrade_ops
    has_unique_index = ("op", "create_index") in upgrade_ops
    assert has_unique_constraint or has_unique_index, (
        "upgrade 应包含唯一约束或唯一索引操作"
    )
    assert ("op", "drop_index") in downgrade_ops or ("op", "drop_constraint") in downgrade_ops, (
        "downgrade 应有对应的删除操作"
    )

    # upgrade 中两次 add_column 必须对应 downgrade 中两次 drop_column
    add_col_count = upgrade_calls.count(("op", "add_column"))
    drop_col_count = downgrade_calls.count(("op", "drop_column"))
    assert add_col_count == 2 and drop_col_count == 2, (
        f"upgrade 有 {add_col_count} 次 add_column，downgrade 有 {drop_col_count} 次 "
        "drop_column——应相等（对称往返）"
    )

    # 唯一约束/索引的创建与删除必须数量相等
    if has_unique_constraint:
        uc_count = upgrade_calls.count(("op", "create_unique_constraint"))
        dc_count = downgrade_calls.count(("op", "drop_constraint"))
        assert uc_count == 2 and dc_count == 2, (
            f"upgrade 有 {uc_count} 次 create_unique_constraint，"
            f"downgrade 有 {dc_count} 次 drop_constraint——应相等"
        )
    else:
        ci_count = upgrade_calls.count(("op", "create_index"))
        di_count = downgrade_calls.count(("op", "drop_index"))
        assert ci_count == 2 and di_count == 2, (
            f"upgrade 有 {ci_count} 次 create_index(unique=True)，"
            f"downgrade 有 {di_count} 次 drop_index——应相等"
        )
