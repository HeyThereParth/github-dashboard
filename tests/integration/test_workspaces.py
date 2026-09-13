"""Workspace creation, ownership, atomicity, listing, and retrieval tests."""

import uuid

from app.integrations.auth.verifier import VerifiedIdentity
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from sqlalchemy import select


def test_authenticated_user_can_create_workspace(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1")
    response = client.post(
        "/api/v1/workspaces", json={"name": "My Workspace"}, headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Workspace"
    assert body["id"]


def test_creator_becomes_owner(client, verifier, auth_headers, db) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1", email="owner@example.com")
    response = client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth_headers)
    workspace_id = uuid.UUID(response.json()["id"])

    membership = (
        db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
        .scalars()
        .one()
    )
    assert membership.role == "owner"

    user = db.execute(select(User).where(User.auth_provider_user_id == "ext-1")).scalars().one()
    assert membership.user_id == user.id


def test_workspace_creation_is_atomic(client, verifier, auth_headers, db) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1")
    response = client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth_headers)
    workspace_id = uuid.UUID(response.json()["id"])

    workspaces = db.execute(select(Workspace)).scalars().all()
    members = (
        db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id))
        .scalars()
        .all()
    )
    assert len(workspaces) == 1
    assert len(members) == 1  # a workspace must never exist without its owner


def test_authenticated_user_can_list_workspaces(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1")
    client.post("/api/v1/workspaces", json={"name": "A"}, headers=auth_headers)
    client.post("/api/v1/workspaces", json={"name": "B"}, headers=auth_headers)

    response = client.get("/api/v1/workspaces", headers=auth_headers)
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {"A", "B"}


def test_member_can_retrieve_workspace(client, verifier, auth_headers) -> None:
    verifier.identity = VerifiedIdentity(external_user_id="ext-1")
    created = client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth_headers)
    workspace_id = created.json()["id"]

    response = client.get(f"/api/v1/workspaces/{workspace_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == workspace_id
