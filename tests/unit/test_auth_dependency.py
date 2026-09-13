"""Authentication dependency tests (no database required).

These exercise the 401 paths of the authentication dependency. The provider
verification boundary is stubbed so no Supabase service is contacted.
"""

from collections.abc import Iterator

import pytest
from app.core.security import get_token_verifier
from app.integrations.auth.exceptions import InvalidTokenError
from app.integrations.auth.verifier import TokenVerifier, VerifiedIdentity
from app.main import app
from fastapi.testclient import TestClient


class _AlwaysInvalidVerifier(TokenVerifier):
    """A verifier that rejects every token, for exercising the 401 path."""

    async def verify(self, token: str) -> VerifiedIdentity:
        raise InvalidTokenError("invalid token")


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_token_verifier] = lambda: _AlwaysInvalidVerifier()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_me_rejects_wrong_scheme(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


def test_me_rejects_empty_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer"})
    assert response.status_code == 401


def test_me_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401
