"""Unit tests for pull request synchronization service and routes."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.integrations.github.client import GitHubPullRequestData
from app.main import app
from app.models.pull_request import PullRequest
from app.models.repository import Repository
from app.models.workspace import Workspace
from app.schemas.pull_request import (
    PullRequestListResponse,
    PullRequestResponse,
)
from app.services.github_service import GitHubNotConnectedError
from app.services.repository_service import RepositoryNotFoundError
from app.services.sync_service import RepositoryNotTrackedError, SyncService
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
def mock_pull_request(repo_id: uuid.UUID) -> PullRequest:
    now = datetime.now(UTC)
    pr = PullRequest(
        repository_id=repo_id,
        github_id=98765,
        node_id="PR_kwDO123",
        number=1,
        title="feat: add ingestion engine",
        state="open",
        draft=False,
        author_login="HeyThereParth",
        html_url="https://github.com/HeyThereParth/github-dashboard/pull/1",
        merged_at=None,
        closed_at=None,
        github_created_at=now,
        github_updated_at=now,
    )
    pr.id = uuid.uuid4()
    pr.created_at = now
    pr.updated_at = now
    return pr


@pytest.fixture
def client(mock_workspace: Workspace) -> Iterator[TestClient]:
    app.dependency_overrides[get_owned_workspace] = lambda: mock_workspace
    app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# SyncService Unit Tests
# ==============================================================================


def test_sync_service_success(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_workspace: Workspace,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_ws_repo = AsyncMock()
        mock_ws_repo.get_by_id.return_value = mock_workspace

        now = datetime.now(UTC)
        mock_client = AsyncMock()
        mock_client.fetch_all_pull_requests.return_value = [
            GitHubPullRequestData(
                github_id=1,
                node_id="PR_1",
                number=10,
                title="PR Title",
                state="open",
                draft=False,
                html_url="https://github.com/test",
                github_created_at=now,
                github_updated_at=now,
            )
        ]

        mock_pr_repo = AsyncMock()
        mock_pr_repo.upsert_batch.return_value = 1

        service = SyncService(
            pull_request_repo=mock_pr_repo,
            repository_repo=mock_repo_repo,
            workspace_repo=mock_ws_repo,
            client=mock_client,
        )

        result = await service.sync_repository_pull_requests(
            mock_db, workspace_id=workspace_id, repository_id=repo_id
        )

        assert result.repository_id == repo_id
        assert result.synced_count == 1
        assert result.status == "completed"
        mock_pr_repo.upsert_batch.assert_called_once()

    asyncio.run(_run())


def test_sync_service_repo_not_tracked(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repository.is_tracked = False

        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        service = SyncService(repository_repo=mock_repo_repo)
        with pytest.raises(RepositoryNotTrackedError):
            await service.sync_repository_pull_requests(
                mock_db, workspace_id=workspace_id, repository_id=repo_id
            )

    asyncio.run(_run())


def test_sync_service_not_connected_to_github(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_workspace: Workspace,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_workspace.github_installation_id = None

        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_ws_repo = AsyncMock()
        mock_ws_repo.get_by_id.return_value = mock_workspace

        service = SyncService(repository_repo=mock_repo_repo, workspace_repo=mock_ws_repo)
        with pytest.raises(GitHubNotConnectedError):
            await service.sync_repository_pull_requests(
                mock_db, workspace_id=workspace_id, repository_id=repo_id
            )

    asyncio.run(_run())


def test_list_pull_requests_service(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
    mock_pull_request: PullRequest,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_pr_repo = AsyncMock()
        mock_pr_repo.list_by_repository.return_value = [mock_pull_request]
        mock_pr_repo.count_by_repository.return_value = 1

        service = SyncService(
            pull_request_repo=mock_pr_repo,
            repository_repo=mock_repo_repo,
        )

        result = await service.list_repository_pull_requests(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, page=1, per_page=50
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].number == 1
        assert result.items[0].title == "feat: add ingestion engine"

    asyncio.run(_run())


# ==============================================================================
# Route Integration Tests
# ==============================================================================


def test_sync_repository_route_success(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    job_id = uuid.uuid4()
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_job.status = "queued"

    with (
        patch(
            "app.api.v1.workspaces.repository_service.get_tracked_repository",
            new=AsyncMock(return_value=mock_repository),
        ),
        patch(
            "app.api.v1.workspaces.sync_job_repository.create",
            new=AsyncMock(return_value=mock_job),
        ),
        patch(
            "app.api.v1.workspaces.task_queue.enqueue_sync_job",
            new=AsyncMock(return_value="redis"),
        ),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/sync"
        response = client.post(url)
        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == str(job_id)
        assert data["status"] == "queued"
        assert "enqueued" in data["message"].lower()


def test_sync_repository_route_not_found(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    with patch(
        "app.api.v1.workspaces.repository_service.get_tracked_repository",
        side_effect=RepositoryNotFoundError("Repository not found in this workspace"),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/sync"
        response = client.post(url)
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


def test_list_repository_pull_requests_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_pull_request: PullRequest,
) -> None:
    pr_response = PullRequestResponse.model_validate(mock_pull_request)
    mock_list_response = PullRequestListResponse(
        items=[pr_response],
        total=1,
        page=1,
        per_page=50,
    )

    with patch(
        "app.api.v1.workspaces.sync_service.list_repository_pull_requests",
        new=AsyncMock(return_value=mock_list_response),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/pull-requests"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["number"] == 1
        assert data["items"][0]["author_login"] == "HeyThereParth"
