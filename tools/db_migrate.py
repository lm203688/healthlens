"""
HealthLens 数据库迁移工具

用法：
  python tools/db_migrate.py init       # 创建所有表
  python tools/db_migrate.py init --force  # 强制重建（会删除已有表）
  python tools/db_migrate.py seed       # 插入种子数据
  python tools/db_migrate.py migrate    # init + seed 完整执行
  python tools/db_migrate.py status     # 检查数据库连接和表状态
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _import_models():
    """延迟导入所有 ORM 模型，确保 Base.metadata 注册所有表。"""
    from app.models.user import User
    from app.models.observation import HealthObservation
    from app.models.tcm_profile import TcmProfile
    from app.models.tcm_tongue import TongueImage
    from app.models.tcm_syndrome import TcmSyndromeDiagnosis
    from app.models.tcm_formula import (
        TcmFormulaRecommendation,
        TcmFormulaLibrary,
        TcmHerb,
        TcmDeliveryOrder,
    )
    from app.models.diagnosis import DiagnosisResult
    from app.models.health_record import HealthProfile
    from app.models.health_goal import HealthGoal
    from app.models.medication import MedicationRecommendation
    from app.models.prescription import Prescription
    from app.models.notification import Notification
    from app.models.medication_adherence import MedicationAdherence
    from app.models.genomics import PharmacogenomicProfile
    from app.models.data_connection import DataConnection
    from app.models.risk_assessment import RiskAssessment
    from app.models.record import HealthRecord
    from app.models.base import Base

    return Base


def _get_engine():
    """获取同步引擎用于 DDL 操作。"""
    from sqlalchemy import create_engine, text
    from app.config import settings

    url = settings.DATABASE_URL
    if "+aiosqlite" in url:
        url = url.replace("sqlite+aiosqlite", "sqlite")
    elif "+asyncpg" in url:
        url = url.replace("+asyncpg", "psycopg2")

    args = {"connect_args": {"check_same_thread": False}} if "sqlite" in url else {}
    return create_engine(url, **args), text


async def init_schema(force: bool = False):
    """创建所有 ORM 表。"""
    from sqlalchemy import text
    from app.database import engine
    from app.models.base import Base

    Base = _import_models()
    async with engine.begin() as conn:
        if force:
            print("[INFO] 强制重建 — 删除所有已有表...")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 打印表名
    async with engine.connect() as conn:
        if "sqlite" in str(engine.url):
            tables = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        else:
            tables = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            )
        names = [row[0] for row in tables.fetchall()]
        print(f"[OK] 已创建/验证 {len(names)} 张表: {', '.join(sorted(names)[:20])}")


def seed_data():
    """插入种子数据（同步方式）。"""
    Base = _import_models()

    from sqlalchemy import create_engine
    from app.config import settings
    from app.models.user import User
    from app.models.observation import HealthObservation
    from app.models.tcm_profile import TcmProfile
    from app.models.health_goal import HealthGoal
    from app.models.notification import Notification
    from app.models.data_connection import DataConnection
    from datetime import datetime

    url = settings.DATABASE_URL
    if "+aiosqlite" in url:
        url = url.replace("sqlite+aiosqlite", "sqlite")
    elif "+asyncpg" in url:
        url = url.replace("+asyncpg", "psycopg2")

    args = {"connect_args": {"check_same_thread": False}} if "sqlite" in url else {}
    sync_engine = create_engine(url, **args)

    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=sync_engine)
    db = Session()

    try:
        # 1. 创建示例用户
        from app.utils.security import hash_password

        users = [
            ("demo@healthlens.cc", "demo123", "张明", "13800000001"),
            ("user@example.com", "user123", "李丽", "13800000002"),
        ]
        created_users = []
        for email, pwd, name, phone in users:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                print(f"[SKIP] 用户已存在: {email}")
                created_users.append(existing)
            else:
                user = User(
                    id=str(uuid4()),
                    email=email,
                    password_hash=hash_password(pwd),
                    phone=phone,
                    role="user",
                )
                db.add(user)
                created_users.append(user)
                print(f"[OK] 创建用户: {email}")

        db.commit()

        # 2. 创建健康目标
        goals = [
            ("每日步行 8000 步", "steps", "步"),
            ("早睡 23:00 前", "sleep", "小时"),
            ("每日饮水 2000ml", "hydration", "ml"),
        ]
        if created_users:
            u = created_users[0]
            from datetime import timedelta as _td
            now_dt = datetime.utcnow()
            for goal_name, goal_type, unit in goals:
                existing = db.query(HealthGoal).filter(
                    HealthGoal.user_id == u.id,
                    HealthGoal.goal_name == goal_name,
                ).first()
                if not existing:
                    goal = HealthGoal(
                        id=str(uuid4()),
                        user_id=u.id,
                        goal_type=goal_type,
                        goal_name=goal_name,
                        target_value=100.0,
                        current_value=0.0,
                        unit=unit,
                        start_date=now_dt,
                        target_date=now_dt + _td(days=30),
                        status="active",
                        is_reminder_enabled=True,
                    )
                    db.add(goal)
            print(f"[OK] 创建健康目标: {len(goals)} 条")

        # 3. 创建通知
        now = datetime.utcnow()
        notifications = [
            (u.id, "system", "欢迎使用 HealthLens", "完成首次健康评估，了解您的身体状况", "info"),
            (u.id, "health_alert", "每日健康打卡提醒", "记录今日血压、血糖等指标", "info"),
            (u.id, "tcm", "中医体质辨识", "花 3 分钟完成体质问卷，获取个性化调理建议", "info"),
        ]
        for uid, category, title, body, severity in notifications:
            n = Notification(
                id=str(uuid4()),
                user_id=uid,
                category=category,
                title=title,
                content=body,
                severity=severity,
                is_read=False,
                created_at=now,
            )
            db.add(n)
        print(f"[OK] 创建通知: {len(notifications)} 条")

        # 4. 创建数据连接（模拟）
        if created_users:
            u = created_users[0]
            conn = DataConnection(
                id=str(uuid4()),
                user_id=u.id,
                source_type="manual",
                config={"description": "手动打卡"},
                sync_status="active",
                is_active=True,
                created_at=now,
            )
            db.add(conn)
            print(f"[OK] 创建数据连接: 1 条")

        db.commit()
        print("[OK] 种子数据插入完成")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 种子数据插入失败: {e}")
        raise
    finally:
        db.close()


def check_status():
    """检查数据库状态。"""
    from sqlalchemy import create_engine, text
    from app.config import settings

    url = settings.DATABASE_URL
    if "+aiosqlite" in url:
        url = url.replace("sqlite+aiosqlite", "sqlite")
    elif "+asyncpg" in url:
        url = url.replace("+asyncpg", "psycopg2")

    args = {"connect_args": {"check_same_thread": False}} if "sqlite" in url else {}
    engine = create_engine(url, **args)

    try:
        with engine.connect() as conn:
            print(f"[OK] 数据库连接成功: {settings.DATABASE_URL}")
            if "sqlite" in url:
                tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            else:
                tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")).fetchall()
            names = [t[0] for t in tables]
            if names:
                print(f"[INFO] 已有 {len(names)} 张表: {', '.join(names[:20])}")
            else:
                print("[INFO] 数据库为空，尚未建表")
    except Exception as e:
        print(f"[ERROR] 数据库连接失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HealthLens 数据库迁移工具")
    parser.add_argument("command", choices=["init", "seed", "migrate", "status"])
    parser.add_argument("--force", action="store_true", help="强制重建所有表")
    args = parser.parse_args()

    if args.command == "status":
        check_status()
    elif args.command == "init":
        asyncio.run(init_schema(force=args.force))
    elif args.command == "seed":
        seed_data()
    elif args.command == "migrate":
        asyncio.run(init_schema(force=args.force))
        seed_data()
