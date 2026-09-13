"""Unit tests for workspace GitHub integration routes."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.core.config import settings
from app.integrations.github.client import GitHubRepositoryData
from app.main import app
from app.models.workspace import Workspace
from app.services.github_service import GitHubNotConnectedError
from fastapi.testclient import TestClient


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_workspace(workspace_id: uuid.UUID) -> Workspace:
    now = datetime.now(UTC)
    workspace = Workspace(name="Test Workspace")
    workspace.id = workspace_id
    workspace.github_installation_id = None
    workspace.created_at = now
    workspace.updated_at = now
    return workspace


@pytest.fixture
def client(mock_workspace: Workspace) -> Iterator[TestClient]:
    app.dependency_overrides[get_owned_workspace] = lambda: mock_workspace
    app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_install_url(client: TestClient, workspace_id: uuid.UUID) -> None:
    with patch.object(settings, "github_app_slug", "test-github-app"):
        response = client.get(f"/api/v1/workspaces/{workspace_id}/github/install-url")
        assert response.status_code == 200
        data = response.json()
        assert "install_url" in data
        assert "test-github-app" in data["install_url"]
        assert str(workspace_id) in data["install_url"]


def test_connect_github_installation(
    client: TestClient, workspace_id: uuid.UUID, mock_workspace: Workspace
) -> None:
    now = datetime.now(UTC)
    connected = Workspace(name="Test Workspace")
    connected.id = workspace_id
    connected.github_installation_id = 998877
    connected.created_at = now
    connected.updated_at = now

    with patch(
        "app.api.v1.workspaces.github_service.connect_installation",
        new=AsyncMock(return_value=connected),
    ):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/github/connect",
            json={"installation_id": 998877},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["github_installation_id"] == 998877
        assert data["is_github_connected"] is True


def test_disconnect_github_installation(
    client: TestClient, workspace_id: uuid.UUID, mock_workspace: Workspace
) -> None:
    now = datetime.now(UTC)
    mock_workspace.github_installation_id = 998877
    disconnected = Workspace(name="Test Workspace")
    disconnected.id = workspace_id
    disconnected.github_installation_id = None
    disconnected.created_at = now
    disconnected.updated_at = now

    with patch(
        "app.api.v1.workspaces.github_service.disconnect_installation",
        new=AsyncMock(return_value=disconnected),
    ):
        response = client.delete(f"/api/v1/workspaces/{workspace_id}/github/disconnect")
        assert response.status_code == 200
        data = response.json()
        assert data["github_installation_id"] is None
        assert data["is_github_connected"] is False


def test_list_workspace_repositories_success(client: TestClient, workspace_id: uuid.UUID) -> None:
    fake_repos = [
        GitHubRepositoryData(
            github_id=1,
            node_id="R_1",
            name="repo-one",
            full_name="org/repo-one",
            private=True,
            html_url="https://github.com/org/repo-one",
            default_branch="main",
            description="First repo",
        )
    ]

    with patch(
        "app.api.v1.workspaces.github_service.list_workspace_repositories",
        new=AsyncMock(return_value=fake_repos),
    ):
        response = client.get(f"/api/v1/workspaces/{workspace_id}/github/repositories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "repo-one"
        assert data[0]["full_name"] == "org/repo-one"


def test_list_workspace_repositories_not_connected(
    client: TestClient, workspace_id: uuid.UUID
) -> None:
    with patch(
        "app.api.v1.workspaces.github_service.list_workspace_repositories",
        side_effect=GitHubNotConnectedError("Workspace is not connected to GitHub"),
    ):
        response = client.get(f"/api/v1/workspaces/{workspace_id}/github/repositories")
        assert response.status_code == 400
        assert "Workspace is not connected to GitHub" in response.json()["detail"]
