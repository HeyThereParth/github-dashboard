"""Unit tests for background sync jobs: Repository, Queue, Task, and Routes."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.main import app
from app.models.repository import Repository
from app.models.sync_job import SyncJob
from app.models.workspace import Workspace
from app.repositories.sync_job_repository import SyncJobRepository
from app.schemas.pull_request import SyncResultResponse
from app.workers.queue import TaskQueue
from app.workers.tasks.sync_task import run_sync_job
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def repo_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def job_id() -> uuid.UUID:
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
def mock_sync_job(workspace_id: uuid.UUID, repo_id: uuid.UUID, job_id: uuid.UUID) -> SyncJob:
    now = datetime.now(UTC)
    job = SyncJob(
        workspace_id=workspace_id,
        repository_id=repo_id,
        status="queued",
        total_synced=0,
    )
    job.id = job_id
    job.created_at = now
    job.updated_at = now
    return job


@pytest.fixture
def client(mock_workspace: Workspace) -> Iterator[TestClient]:
    app.dependency_overrides[get_owned_workspace] = lambda: mock_workspace
    app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ==============================================================================
# 1. SyncJobRepository Tests
# ==============================================================================


def test_sync_job_repository_create(workspace_id: uuid.UUID, repo_id: uuid.UUID) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        repo = SyncJobRepository()

        job = await repo.create(
            mock_db,
            workspace_id=workspace_id,
            repository_id=repo_id,
            status="queued",
        )

        mock_db.add.assert_called_once_with(job)
        mock_db.flush.assert_awaited_once()
        assert job.workspace_id == workspace_id
        assert job.repository_id == repo_id
        assert job.status == "queued"
        assert job.total_synced == 0

    asyncio.run(_run())


def test_sync_job_repository_transitions(
    mock_sync_job: SyncJob,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        repo = SyncJobRepository()

        # Transition: queued -> processing
        processing_job = await repo.mark_processing(mock_db, job=mock_sync_job)
        assert processing_job.status == "processing"
        assert processing_job.started_at is not None

        # Transition: processing -> completed
        completed_job = await repo.mark_completed(mock_db, job=processing_job, total_synced=42)
        assert completed_job.status == "completed"
        assert completed_job.total_synced == 42
        assert completed_job.completed_at is not None

        # Transition: mark_failed
        failed_job = await repo.mark_failed(
            mock_db, job=mock_sync_job, error_message="Rate limited"
        )
        assert failed_job.status == "failed"
        assert failed_job.error_message == "Rate limited"

    asyncio.run(_run())


# ==============================================================================
# 2. TaskQueue Tests (Redis vs. In-Process Fallback)
# ==============================================================================


def test_task_queue_enqueue_redis_success(
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_redis_client = AsyncMock()
        mock_redis_manager = MagicMock()
        mock_redis_manager.get_client.return_value = mock_redis_client

        queue = TaskQueue(redis=mock_redis_manager)
        backend = await queue.enqueue_sync_job(
            job_id=job_id,
            workspace_id=workspace_id,
            repository_id=repo_id,
        )

        assert backend == "redis"
        mock_redis_client.lpush.assert_awaited_once()
        args = mock_redis_client.lpush.call_args[0]
        assert args[0] == "github_intel:queue:sync_jobs"
        payload = json.loads(args[1])
        assert payload["job_id"] == str(job_id)
        assert payload["repository_id"] == str(repo_id)

    asyncio.run(_run())


def test_task_queue_enqueue_redis_fallback(
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_redis_client = AsyncMock()
        mock_redis_client.lpush.side_effect = RedisConnectionError("Cannot connect")
        mock_redis_manager = MagicMock()
        mock_redis_manager.get_client.return_value = mock_redis_client

        def _fake_create_task(coro: object) -> MagicMock:
            if asyncio.iscoroutine(coro):
                coro.close()
            return MagicMock()

        with patch("asyncio.create_task", side_effect=_fake_create_task) as mock_create_task:
            queue = TaskQueue(redis=mock_redis_manager)
            backend = await queue.enqueue_sync_job(
                job_id=job_id,
                workspace_id=workspace_id,
                repository_id=repo_id,
            )

            assert backend == "in_process"
            mock_create_task.assert_called_once()

    asyncio.run(_run())


# ==============================================================================
# 3. Sync Task Runner Tests
# ==============================================================================


def test_run_sync_job_success(
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_sync_job: SyncJob,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db

        mock_job_repo = AsyncMock()
        mock_job_repo.get_by_id.return_value = mock_sync_job

        mock_service = AsyncMock()
        mock_service.sync_repository_pull_requests.return_value = SyncResultResponse(
            repository_id=repo_id,
            synced_count=12,
            status="completed",
        )

        with patch("app.workers.tasks.sync_task.async_session_factory", mock_session_factory):
            await run_sync_job(
                job_id=job_id,
                workspace_id=workspace_id,
                repository_id=repo_id,
                job_repo=mock_job_repo,
                service=mock_service,
            )

        mock_job_repo.mark_processing.assert_awaited_once_with(mock_db, job=mock_sync_job)
        mock_job_repo.mark_completed.assert_awaited_once_with(
            mock_db, job=mock_sync_job, total_synced=12
        )
        assert mock_db.commit.await_count >= 2

    asyncio.run(_run())


def test_run_sync_job_failure(
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_sync_job: SyncJob,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db

        mock_job_repo = AsyncMock()
        mock_job_repo.get_by_id.return_value = mock_sync_job

        mock_service = AsyncMock()
        mock_service.sync_repository_pull_requests.side_effect = RuntimeError("Network timeout")

        with patch("app.workers.tasks.sync_task.async_session_factory", mock_session_factory):
            await run_sync_job(
                job_id=job_id,
                workspace_id=workspace_id,
                repository_id=repo_id,
                job_repo=mock_job_repo,
                service=mock_service,
            )

        mock_db.rollback.assert_awaited_once()
        mock_job_repo.mark_failed.assert_awaited_once_with(
            mock_db, job=mock_sync_job, error_message="Network timeout"
        )

    asyncio.run(_run())


# ==============================================================================
# 4. Sync Job Route Tests (Polling & History)
# ==============================================================================


def test_get_sync_job_route_success(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    job_id: uuid.UUID,
    mock_repository: Repository,
    mock_sync_job: SyncJob,
) -> None:
    with (
        patch(
            "app.api.v1.workspaces.repository_service.get_tracked_repository",
            new=AsyncMock(return_value=mock_repository),
        ),
        patch(
            "app.api.v1.workspaces.sync_job_repository.get_by_id",
            new=AsyncMock(return_value=mock_sync_job),
        ),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/sync-jobs/{job_id}"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(job_id)
        assert data["workspace_id"] == str(workspace_id)
        assert data["repository_id"] == str(repo_id)
        assert data["status"] == "queued"


def test_get_sync_job_route_not_found(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    job_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    with (
        patch(
            "app.api.v1.workspaces.repository_service.get_tracked_repository",
            new=AsyncMock(return_value=mock_repository),
        ),
        patch(
            "app.api.v1.workspaces.sync_job_repository.get_by_id",
            new=AsyncMock(return_value=None),
        ),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/sync-jobs/{job_id}"
        response = client.get(url)
        assert response.status_code == 404
        assert "Sync job not found" in response.json()["detail"]


def test_list_sync_jobs_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
    mock_sync_job: SyncJob,
) -> None:
    with (
        patch(
            "app.api.v1.workspaces.repository_service.get_tracked_repository",
            new=AsyncMock(return_value=mock_repository),
        ),
        patch(
            "app.api.v1.workspaces.sync_job_repository.list_for_repository",
            new=AsyncMock(return_value=[mock_sync_job]),
        ),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/sync-jobs"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(mock_sync_job.id)
        assert data[0]["status"] == "queued"
