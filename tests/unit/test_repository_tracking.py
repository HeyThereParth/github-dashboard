"""Unit tests for repository tracking routes."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.main import app
from app.models.repository import Repository
from app.models.workspace import Workspace
from app.services.github_service import GitHubNotConnectedError
from app.services.repository_service import RepositoryNotFoundError
from fastapi.testclient import TestClient


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def repo_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_workspace(workspace_id: uuid.UUID) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(name="Test Workspace")
    workspace.id = workspace_id
    workspace.github_installation_id = 998877
    workspace.created_at = now
    workspace.updated_at = now
    return workspace


@pytest.fixture
def mock_repository(workspace_id: uuid.UUID, repo_id: uuid.UUID) -> Repository:
    now = datetime.now(UTC)
    repo = Repository(
        workspace_id=workspace_id,
        github_id=12345,
        node_id="R_test123",
        name="github-dashboard",
        full_name="HeyThereParth/github-dashboard",
        owner_login="HeyThereParth",
        private=False,
        html_url="https://github.com/HeyThereParth/github-dashboard",
        default_branch="main",
        description="Dashboard repo",
        is_tracked=True,
    )
    repo.id = repo_id
    repo.created_at = now
    repo.updated_at = now
    return repo


@pytest.fixture
def client(mock_workspace: Workspace) -> Iterator[TestClient]:
    app.dependency_overrides[get_owned_workspace] = lambda: mock_workspace
    app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_track_repository_success(
    client: TestClient, workspace_id: uuid.UUID, mock_repository: Repository
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.track_repository",
        new=AsyncMock(return_value=mock_repository),
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/repositories/track",
            json={"owner": "HeyThereParth", "repo": "github-dashboard"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "github-dashboard"
        assert data["full_name"] == "HeyThereParth/github-dashboard"
        assert data["is_tracked"] is True
        assert data["github_id"] == 12345


def test_track_repository_not_connected(client: TestClient, workspace_id: uuid.UUID) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.track_repository",
        side_effect=GitHubNotConnectedError("Workspace is not connected to GitHub"),
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/repositories/track",
            json={"owner": "HeyThereParth", "repo": "github-dashboard"},
        )
        assert response.status_code == 400
        assert "Workspace is not connected to GitHub" in response.json()["detail"]


def test_list_tracked_repositories(
    client: TestClient, workspace_id: uuid.UUID, mock_repository: Repository
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.list_tracked_repositories",
        new=AsyncMock(return_value=[mock_repository]),
    ):
        response = client.get(f"/api/v1/workspaces/{workspace_id}/repositories/tracked")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "github-dashboard"
        assert data[0]["is_tracked"] is True


def test_get_tracked_repository_success(
    client: TestClient, workspace_id: uuid.UUID, repo_id: uuid.UUID, mock_repository: Repository
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.get_tracked_repository",
        new=AsyncMock(return_value=mock_repository),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "github-dashboard"
        assert data["id"] == str(repo_id)


def test_get_tracked_repository_not_found(
    client: TestClient, workspace_id: uuid.UUID, repo_id: uuid.UUID
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.get_tracked_repository",
        side_effect=RepositoryNotFoundError("Repository not found in this workspace"),
    ):
        response = client.get(f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}")
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


def test_untrack_repository_success(
    client: TestClient, workspace_id: uuid.UUID, repo_id: uuid.UUID
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.untrack_repository",
        new=AsyncMock(return_value=None),
    ):
        response = client.delete(
            f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}"
        )
        assert response.status_code == 204
