"""User provisioning lifecycle tests."""

from app.integrations.auth.verifier import VerifiedIdentity
from app.models.user import User
from sqlalchemy import select


def test_first_authenticated_request_creates_user(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(
        external_user_id="ext-1", email="alice@example.com", name="Alice"
    )
    response = client.get("/api/v1/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert body["name"] == "Alice"
    assert body["id"] != "ext-1"  # internal id, not the provider id


def test_subsequent_request_reuses_user(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1", email="alice@example.com")
    first = client.get("/api/v1/me", headers=auth_headers)
    second = client.get("/api/v1/me", headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_duplicate_external_identity_creates_single_user(
    client, verifier, auth_headers, db
) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-dup", email="dup@example.com")
    client.get("/api/v1/me", headers=auth_headers)
    client.get("/api/v1/me", headers=auth_headers)

    rows = db.execute(select(User).where(User.auth_provider_user_id == "ext-dup")).scalars().all()
    assert len(rows) == 1
