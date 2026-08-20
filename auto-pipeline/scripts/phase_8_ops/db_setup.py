"""数据库初始化与连接管理（2026-08-20 新增）

免费数据库方案：
  方案1（推荐）：在现有腾讯云服务器上 Docker 跑 PostgreSQL（零额外费用）
  方案2：本地开发用 SQLite（自动降级，无需安装任何数据库）

优先级链：环境变量 DATABASE_URL > config.database.url > Docker PostgreSQL > SQLite fallback

用法：
  python db_setup.py init      # 初始化数据库（创建表）
  python db_setup.py check     # 检查连接状态
  python db_setup.py migrate   # 执行迁移
"""
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from state_manager import BASE_DIR, log

DB_URL_FALLBACK = "postgresql://healthlens:healthlens@localhost:5432/healthlens"
SQLITE_PATH = BASE_DIR / "healthlens_local.db"


def get_db_url():
    """优先级：环境变量 > config > Docker PostgreSQL 默认"""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("database", {}).get("url", "")
        if url:
            return url
    except Exception:
        pass
    return DB_URL_FALLBACK


def is_postgres_available(url=None):
    """检查 PostgreSQL 是否可达"""
    url = url or get_db_url()
    if not url.startswith("postgresql"):
        return False
    try:
        import asyncio
        async def _check():
            try:
                import asyncpg
            except ImportError:
                return False
            try:
                conn = await asyncpg.connect(url, timeout=5)
                await conn.close()
                return True
            except Exception:
                return False
        return asyncio.run(_check())
    except Exception:
        return False


def get_sqlite_conn():
    """获取 SQLite 连接（本地开发 fallback）"""
    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite_tables():
    """在 SQLite 中创建核心表（开发/免费部署用）"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sleep_data TEXT,
            body_data TEXT
        );

        CREATE TABLE IF NOT EXISTS health_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_data TEXT,
            plan TEXT
        );

        CREATE TABLE IF NOT EXISTS point_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            package_code TEXT NOT NULL,
            price_cny REAL NOT NULL,
            payment_status TEXT DEFAULT 'pending',
            payment_method TEXT,
            paid_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS referral_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER REFERENCES users(id),
            invitee_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_user ON health_reports(user_id);
        CREATE INDEX IF NOT EXISTS idx_reports_created ON health_reports(created_at);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON point_orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON point_orders(payment_status);
    """)

    conn.commit()
    conn.close()
    log(f"SQLite 数据库已初始化: {SQLITE_PATH}")
    return True


def init_postgres_tables(url=None):
    """在 PostgreSQL 中创建核心表（需要 asyncpg）"""
    url = url or get_db_url()

    async def _init():
        try:
            import asyncpg
        except ImportError:
            log("asyncpg 未安装，无法初始化 PostgreSQL", level="ERROR")
            return False

        conn = await asyncpg.connect(url)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sleep_data JSONB,
                body_data JSONB
            );

            CREATE TABLE IF NOT EXISTS health_reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                report_data JSONB,
                plan JSONB
            );

            CREATE TABLE IF NOT EXISTS point_orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                package_code VARCHAR(100) NOT NULL,
                price_cny DECIMAL(10,2) NOT NULL,
                payment_status VARCHAR(50) DEFAULT 'pending',
                payment_method VARCHAR(50),
                paid_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS referral_events (
                id SERIAL PRIMARY KEY,
                referrer_id INTEGER REFERENCES users(id),
                invitee_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at);
            CREATE INDEX IF NOT EXISTS idx_reports_user ON health_reports(user_id);
            CREATE INDEX IF NOT EXISTS idx_reports_created ON health_reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON point_orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON point_orders(payment_status);
        """)
        await conn.close()
        return True

    import asyncio
    return asyncio.run(_init())


def check_db_status():
    """检查数据库连接状态"""
    url = get_db_url()
    pg_available = is_postgres_available(url)

    status = {
        "url": url[:30] + "..." if len(url) > 30 else url,
        "type": "postgresql" if url.startswith("postgresql") else "other",
        "postgres_available": pg_available,
        "sqlite_path": str(SQLITE_PATH),
        "sqlite_exists": SQLITE_PATH.exists(),
    }

    if pg_available:
        status["recommendation"] = "PostgreSQL 可用，使用 PostgreSQL"
        status["active_db"] = "postgresql"
    else:
        status["recommendation"] = "PostgreSQL 不可用，使用 SQLite fallback"
        status["active_db"] = "sqlite"

    return status


def run():
    """初始化数据库（PostgreSQL 或 SQLite）"""
    url = get_db_url()
    log(f"数据库连接串: {url[:30]}...")

    if is_postgres_available(url):
        log("检测到 PostgreSQL，初始化 PostgreSQL 表...")
        ok = init_postgres_tables(url)
        if ok:
            log("PostgreSQL 初始化完成")
            return True
        log("PostgreSQL 初始化失败，降级到 SQLite", level="WARN")

    log("使用 SQLite fallback（本地开发/免费部署）")
    ok = init_sqlite_tables()
    if ok:
        log(f"SQLite 初始化完成: {SQLITE_PATH}")
    return ok


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "init":
        ok = run()
        sys.exit(0 if ok else 1)
    elif cmd == "check":
        status = check_db_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
    elif cmd == "migrate":
        log("迁移：当前使用 CREATE IF NOT EXISTS，无需额外迁移步骤")
    else:
        print(f"用法: python db_setup.py [init|check|migrate]")
        sys.exit(1)
