import asyncio
import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.models.base import Base
from app.database import get_db
from app.config import settings

# 【2026-10-27 P0-QA-01】Windows 子进程 GBK 解码修复：任何由测试/工具脚本
# 派生的 Python 子进程，其 stdout/stderr 若为管道（capture_output），在
# Windows 默认区域（GBK/cp936）下可能输出 UTF-8 中文字符而解码失败，或
# 子进程自身因 stdout 编码为 GBK 而抛 UnicodeEncodeError。
# 在 conftest 顶层设置 PYTHONIOENCODING=utf-8：父进程（pytest）继承该
# 环境变量，所有未显式传 env 的 subprocess.run 子进程也会继承，从而保证
# 子进程以 UTF-8 输出、父进程以 UTF-8 解码（配合各调用点的
# encoding="utf-8", errors="replace"）。
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 测试环境统一使用 mock OCR 引擎
settings.OCR_ENGINE = "mock"

# 测试环境禁用限流（避免注册/登录频次超限）
settings.RATE_LIMIT_ENABLED = False
try:
    from app.api.auth import limiter
    limiter.enabled = False
except ImportError:
    pass

TEST_DATABASE_URL = "sqlite+aiosqlite://"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def test_user_data():
    """每个测试用唯一的 email/account，避免并发冲突。

    B0-1（2026-10-12）：`LoginInput` schema 已从 `email` 迁到 `account`
    （同时接受邮箱或手机号）；此 fixture 同时提供两个字段，保证注册/登录
    端点各自的校验都能通过。
    """
    _email = f"test_{uuid.uuid4().hex[:8]}@healthlens.com"
    return {
        "email": _email,
        "account": _email,
        "password": "TestPassword123!",
    }

@pytest.fixture
def test_user_token(test_user_data):
    from app.utils.security import create_access_token
    return create_access_token({
        "sub": str(uuid.uuid4()),
        "email": test_user_data["email"],
    })
