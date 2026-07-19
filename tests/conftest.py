import asyncio
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.models.base import Base
from app.database import get_db
from app.config import settings

# 测试环境统一使用 mock OCR 引擎
settings.OCR_ENGINE = "mock"

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
    """每个测试用唯一的 email，避免并发冲突"""
    return {
        "email": f"test_{uuid.uuid4().hex[:8]}@healthlens.com",
        "password": "TestPassword123!",
    }

@pytest.fixture
def test_user_token(test_user_data):
    from app.utils.security import create_access_token
    return create_access_token({
        "sub": str(uuid.uuid4()),
        "email": test_user_data["email"],
    })
