"""Workspace authorization and tenant isolation tests."""

from app.integrations.auth.verifier import VerifiedIdentity


def test_unauthenticated_cannot_access_protected_endpoints(client) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/workspaces").status_code == 401
    assert client.post("/api/v1/workspaces", json={"name": "W"}).status_code == 401


def test_non_member_cannot_access_workspace(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="owner")
    created = client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth_headers)
    workspace_id = created.json()["id"]

    verifier.identity = VerifiedIdentity(external_user_id="intruder")
    response = client.get(f"/api/v1/workspaces/{workspace_id}", headers=auth_headers)
    assert response.status_code == 403


def test_member_can_access_workspace(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="owner")
    created = client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth_headers)
    workspace_id = created.json()["id"]

    response = client.get(f"/api/v1/workspaces/{workspace_id}", headers=auth_headers)
    assert response.status_code == 200


def test_tenant_isolation_between_users(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="user-a", email="a@example.com")
    ws_a = client.post(
        "/api/v1/workspaces", json={"name": "Workspace A"}, headers=auth_headers
    ).json()

    verifier.identity = VerifiedIdentity(external_user_id="user-b", email="b@example.com")
    ws_b = client.post(
        "/api/v1/workspaces", json={"name": "Workspace B"}, headers=auth_headers
    ).json()

    # User A must not access Workspace B, and vice versa.
    verifier.identity = VerifiedIdentity(external_user_id="user-a", email="a@example.com")
    assert client.get(f"/api/v1/workspaces/{ws_b['id']}", headers=auth_headers).status_code == 403

    verifier.identity = VerifiedIdentity(external_user_id="user-b", email="b@example.com")
    assert client.get(f"/api/v1/workspaces/{ws_a['id']}", headers=auth_headers).status_code == 403

    # Each user lists only their own workspaces.
    verifier.identity = VerifiedIdentity(external_user_id="user-a", email="a@example.com")
    listed_a = client.get("/api/v1/workspaces", headers=auth_headers).json()
    assert {w["name"] for w in listed_a} == {"Workspace A"}
