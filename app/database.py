from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 同步 Session 工厂 (Celery 任务 + 通知持久化使用)
# 使用延迟导入避免在 asyncpg-only 环境下报错
_SessionLocal = None


def SessionLocal():
    """延迟创建的同步 Session 工厂。

    Celery 任务和通知服务通过 ``from app.database import SessionLocal`` 获取此函数，
    调用 ``db = SessionLocal()`` 即可拿到同步 session。
    首次调用时才创建引擎，避免 import 时就需要 psycopg2。
    """
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        _sync_url = settings.DATABASE_URL
        if "+asyncpg" in _sync_url:
            _sync_url = _sync_url.replace("+asyncpg", "+psycopg2")
        elif "+aiosqlite" in _sync_url:
            _sync_url = _sync_url.replace("+aiosqlite", "/sqlite3")
        _engine = create_engine(_sync_url, pool_pre_ping=True)
        _SessionLocal = _sessionmaker(bind=_engine, expire_on_commit=False)
    return _SessionLocal()


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
