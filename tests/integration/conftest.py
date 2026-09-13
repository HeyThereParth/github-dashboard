"""Integration test fixtures.

These require a running PostgreSQL test database. The schema is created once
per session and tables are truncated between tests for isolation. The Supabase
token verification boundary is replaced with an in-memory stub.
"""

import os
import uuid
from collections.abc import AsyncIterator, Generator

import pytest
from app import models  # noqa: F401  (register models on Base.metadata)
from app.core.database import Base, get_db
from app.core.security import get_token_verifier
from app.integrations.auth.exceptions import InvalidTokenError
from app.integrations.auth.verifier import TokenVerifier, VerifiedIdentity
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/github_intelligence_test",
)

_sync_engine = create_engine(TEST_DATABASE_URL)
_async_engine = create_async_engine(TEST_DATABASE_URL)
_async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)
_sync_session_factory = sessionmaker(bind=_sync_engine)


class StubVerifier(TokenVerifier):
    """In-memory verifier that never contacts Supabase."""

    def __init__(self) -> None:
        self.identity = VerifiedIdentity(
            external_user_id=str(uuid.uuid4()), email="test@example.com", name="Test User"
        )
        self.invalid_tokens: set[str] = set()

    async def verify(self, token: str) -> VerifiedIdentity:
        if token in self.invalid_tokens:
            raise InvalidTokenError("invalid token")
        return self.identity


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Generator[None, None, None]:
    Base.metadata.create_all(_sync_engine)
    yield
    Base.metadata.drop_all(_sync_engine)


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None, None, None]:
    statement = text("TRUNCATE workspace_members, workspaces, users RESTART IDENTITY CASCADE")
    with _sync_engine.begin() as conn:
        conn.execute(statement)
    yield
    with _sync_engine.begin() as conn:
        conn.execute(statement)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    with _sync_session_factory() as session:
        yield session


@pytest.fixture()
def verifier() -> StubVerifier:
    return StubVerifier()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture()
def client(verifier: StubVerifier) -> Generator[TestClient, None, None]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with _async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
