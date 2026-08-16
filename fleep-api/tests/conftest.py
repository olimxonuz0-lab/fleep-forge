import asyncio
import os
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fleep:fleep@localhost:5432/fleep_test")

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from core.database import Base
from models.user import User


@pytest_asyncio.fixture
async def async_engine():
    # SQLite in-memory keeps unit tests fast and dependency-free; the
    # PostgreSQL-specific JSONB/UUID columns are exercised separately in
    # the docker-compose based integration test job (see infra/CI).
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncSession:
    session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(display_name="Test User", email=f"{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
