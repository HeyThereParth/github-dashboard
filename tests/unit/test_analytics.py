"""Unit tests for analytics service, cache-aside pattern, and routes."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.core.redis import RedisClient
from app.main import app
from app.models.repository import Repository
from app.models.workspace import Workspace
from app.schemas.analytics import (
    AuthorMetricsResponse,
    CycleTimeMetrics,
    RepositoryMetricsResponse,
    WeeklyThroughputResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.repository_service import RepositoryNotFoundError
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError


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


# ==============================================================================
# Redis Resiliency Tests
# ==============================================================================


def test_redis_soft_fail_on_connection_error() -> None:
    async def _run() -> None:
        client = RedisClient(redis_url="redis://localhost:9999/0")
        mock_aioredis = AsyncMock()
        mock_aioredis.get.side_effect = RedisConnectionError("Cannot connect")
        mock_aioredis.set.side_effect = RedisConnectionError("Cannot connect")

        with patch.object(client, "get_client", return_value=mock_aioredis):
            # Must return None/False without crashing
            get_res = await client.get("any_key")
            assert get_res is None

            set_res = await client.set("any_key", "val")
            assert set_res is False

    asyncio.run(_run())


# ==============================================================================
# AnalyticsService Cache-Aside Tests
# ==============================================================================


def test_analytics_service_cache_hit(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_redis = AsyncMock()

        cached_payload = RepositoryMetricsResponse(
            repository_id=repo_id,
            time_window_days=30,
            total_prs=20,
            open_prs=5,
            merged_prs=12,
            closed_unmerged_prs=3,
            merge_rate_percentage=80.0,
            cycle_time=CycleTimeMetrics(p50_hours=4.5, p90_hours=24.0, avg_hours=8.0),
            cached=False,
        ).model_dump_json()

        mock_redis.get.return_value = cached_payload

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_overview_metrics(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, days=30
        )

        assert result.cached is True
        assert result.total_prs == 20
        assert result.cycle_time.p50_hours == 4.5
        # Verify DB was NOT queried because of cache hit
        mock_analytics_repo.get_overview_metrics.assert_not_called()

    asyncio.run(_run())


def test_analytics_service_cache_miss_computes_and_caches(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_overview_metrics.return_value = {
            "total_prs": 10,
            "open_prs": 2,
            "merged_prs": 7,
            "closed_unmerged_prs": 1,
            "merge_rate_percentage": 87.5,
            "p50_hours": 3.2,
            "p90_hours": 15.0,
            "avg_hours": 5.4,
        }

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache MISS

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_overview_metrics(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, days=30
        )

        assert result.cached is False
        assert result.total_prs == 10
        assert result.merged_prs == 7
        assert result.cycle_time.p50_hours == 3.2
        # Verify DB WAS queried and result WAS saved to Redis
        mock_analytics_repo.get_overview_metrics.assert_called_once()
        mock_redis.set.assert_called_once()

    asyncio.run(_run())


def test_analytics_service_weekly_throughput(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_weekly_throughput.return_value = [
            {"week_start": "2024-03-01T00:00:00", "merged_count": 5},
            {"week_start": "2024-03-08T00:00:00", "merged_count": 8},
        ]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_weekly_throughput(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, weeks=8
        )

        assert result.weeks_analyzed == 8
        assert len(result.data) == 2
        assert result.data[0].merged_count == 5
        assert result.data[1].merged_count == 8

    asyncio.run(_run())


def test_analytics_service_author_metrics(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_author_metrics.return_value = [
            {
                "author_login": "alice",
                "total_prs": 14,
                "merged_prs": 12,
                "avg_cycle_time_hours": 3.8,
            }
        ]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_author_metrics(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, days=30
        )

        assert len(result.authors) == 1
        assert result.authors[0].author_login == "alice"
        assert result.authors[0].merged_prs == 12

    asyncio.run(_run())


# ==============================================================================
# Route Integration Tests
# ==============================================================================


def test_analytics_overview_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    overview_resp = RepositoryMetricsResponse(
        repository_id=repo_id,
        time_window_days=30,
        total_prs=15,
        open_prs=3,
        merged_prs=10,
        closed_unmerged_prs=2,
        merge_rate_percentage=83.3,
        cycle_time=CycleTimeMetrics(p50_hours=2.5, p90_hours=12.0, avg_hours=4.0),
        cached=True,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_overview_metrics",
        new=AsyncMock(return_value=overview_resp),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/analytics/overview"
        response = client.get(url, params={"days": 30})
        assert response.status_code == 200
        data = response.json()
        assert data["total_prs"] == 15
        assert data["cached"] is True
        assert data["cycle_time"]["p50_hours"] == 2.5


def test_analytics_throughput_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    throughput_resp = WeeklyThroughputResponse(
        repository_id=repo_id,
        weeks_analyzed=8,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_weekly_throughput",
        new=AsyncMock(return_value=throughput_resp),
    ):
        url = (
            f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/analytics/throughput"
        )
        response = client.get(url, params={"weeks": 8})
        assert response.status_code == 200
        data = response.json()
        assert data["weeks_analyzed"] == 8


def test_analytics_authors_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    authors_resp = AuthorMetricsResponse(
        repository_id=repo_id,
        time_window_days=30,
        authors=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_author_metrics",
        new=AsyncMock(return_value=authors_resp),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/analytics/authors"
        response = client.get(url, params={"days": 30})
        assert response.status_code == 200
        data = response.json()
        assert data["repository_id"] == str(repo_id)


def test_analytics_overview_not_found(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    with patch(
        "app.api.v1.analytics.analytics_service.get_overview_metrics",
        side_effect=RepositoryNotFoundError("Repository not found in this workspace"),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/analytics/overview"
        response = client.get(url)
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]
