"""
Async database engine and session factory.

We use SQLAlchemy 2.0's async ORM with asyncpg. A single engine is created
per process and reused; sessions are short-lived and created per request via
the `get_db` dependency.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session.

    Commits are the caller's responsibility (usually inside a service /
    transaction-manager function, not the router) so that multi-step
    operations can be wrapped in a single unit of work.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for use outside of request handlers (e.g. in the
    distillation pipeline, scheduled jobs, or scripts)."""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_models() -> None:
    """Create tables. Used in tests and local dev; production uses Alembic
    migrations (see infra/migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
