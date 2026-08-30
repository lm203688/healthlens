from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# 自动设置 connect_args（SQLite 需要 check_same_thread=False）
_connect_args = {}
if "sqlite" in settings.DATABASE_URL:
    _connect_args["check_same_thread"] = False

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
    connect_args=_connect_args,
)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_SessionLocal = None


def SessionLocal():
    """延迟创建的同步 Session 工厂（Celery / 通知持久化用）。"""
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker
        _sync_url = settings.DATABASE_URL
        if "+asyncpg" in _sync_url:
            _sync_url = _sync_url.replace("+asyncpg", "psycopg2")
        elif "+aiosqlite" in _sync_url:
            _sync_url = _sync_url.replace("sqlite+aiosqlite", "sqlite")
        _sync_args = {"connect_args": {"check_same_thread": False}} if "sqlite" in _sync_url else {}
        _engine = create_engine(_sync_url, pool_pre_ping=True, **_sync_args)
        _SessionLocal = _sessionmaker(bind=_engine, expire_on_commit=False)
    return _SessionLocal()


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
