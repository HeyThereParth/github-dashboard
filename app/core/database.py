"""SQLAlchemy database foundation.

Provides the async engine, session factory, declarative base and a FastAPI
dependency for request-scoped sessions. No tables are created automatically;
schema is owned by Alembic (see ``migrations/``).
"""

import asyncio
import sys
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _configure_windows_event_loop() -> None:
    """Use the selector event loop on Windows (required by async psycopg)."""
    if sys.platform != "win32":
        return
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is None:
        return
    try:
        asyncio.set_event_loop_policy(policy_cls())
    except RuntimeError:
        pass  # a loop policy is already active


_configure_windows_event_loop()


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session.

    Commits on success and rolls back on error so that mutations performed by
    a request are persisted atomically.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine and release pooled connections (used on shutdown)."""
    await engine.dispose()
