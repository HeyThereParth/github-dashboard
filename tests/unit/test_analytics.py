"""Unit tests for analytics service, cache-aside pattern, and routes."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.dependencies import get_accessible_workspace, get_owned_workspace
from app.core.redis import RedisClient
from app.main import app
from app.models.repository import Repository
from app.models.workspace import Workspace
from app.repositories.analytics_repository import (
    AnalyticsRepository,
    day_bucket_starts,
    fill_day_counts,
    fill_week_counts,
    fill_week_percentiles,
    week_bucket_starts,
)
from app.schemas.analytics import (
    ActivityTrendItem,
    ActivityTrendResponse,
    AuthorMetricsResponse,
    CycleTimeMetrics,
    CycleTimeTrendItem,
    CycleTimeTrendResponse,
    RepositoryMetricsResponse,
    WeeklyThroughputResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.repository_service import RepositoryNotFoundError
from fastapi import HTTPException, status
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


# ==============================================================================
# Time-Series Helper Tests (bucket alignment / gap-filling)
# ==============================================================================


def test_week_bucket_starts_align_to_monday() -> None:
    now = datetime(2026, 9, 16, 14, 30, tzinfo=UTC)  # Wednesday
    starts = week_bucket_starts(now, 4)
    assert len(starts) == 4
    assert all(start.weekday() == 0 for start in starts)  # All Mondays
    assert starts[-1] == datetime(2026, 9, 14)
    assert starts[0] == datetime(2026, 8, 24)


def test_fill_week_counts_zero_fills_and_marks_partial() -> None:
    starts = week_bucket_starts(datetime(2026, 9, 16, tzinfo=UTC), 3)
    counts = {starts[1]: 5}
    series = fill_week_counts(counts, starts)
    assert [item["merged_count"] for item in series] == [0, 5, 0]
    assert series[1]["week_start"] == starts[1].isoformat()
    assert series[0]["is_partial"] is False
    assert series[-1]["is_partial"] is True


def test_fill_day_counts_zero_fills_missing_days() -> None:
    starts = day_bucket_starts(datetime(2026, 9, 16, 8, 0, tzinfo=UTC), 3)
    series = fill_day_counts({starts[0]: 2}, {starts[2]: 1}, starts)
    assert series[0] == {"day": starts[0].isoformat(), "created_count": 2, "merged_count": 0}
    assert series[1] == {"day": starts[1].isoformat(), "created_count": 0, "merged_count": 0}
    assert series[2]["merged_count"] == 1


def test_fill_week_percentiles_preserves_empty_week_gaps() -> None:
    starts = week_bucket_starts(datetime(2026, 9, 16, tzinfo=UTC), 2)
    rows = {starts[0]: {"p50_hours": 1.5, "p90_hours": 9.0, "avg_hours": 3.0}}
    series = fill_week_percentiles(rows, starts)
    assert series[0]["p50_hours"] == 1.5
    assert series[0]["is_partial"] is False
    assert series[1]["p50_hours"] is None
    assert series[1]["p90_hours"] is None
    assert series[1]["is_partial"] is True


# ==============================================================================
# Cache Invalidation Tests
# ==============================================================================


def test_invalidate_repository_cache_clears_all_metric_prefixes() -> None:
    async def _run() -> None:
        mock_redis = AsyncMock()
        service = AnalyticsService(
            analytics_repo=AsyncMock(),
            repository_repo=AsyncMock(),
            redis=mock_redis,
        )
        repo = uuid.uuid4()
        await service.invalidate_repository_cache(repo)

        prefixes = [call.args[0] for call in mock_redis.delete_prefix.await_args_list]
        assert prefixes == [
            f"analytics:overview:{repo}",
            f"analytics:throughput:{repo}",
            f"analytics:authors:{repo}",
            f"analytics:activity:{repo}",
            f"analytics:cycletime:{repo}",
        ]

    asyncio.run(_run())


# ==============================================================================
# Activity / Cycle-Time Trend Service Tests
# ==============================================================================


def test_analytics_service_activity_trend(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_daily_activity.return_value = [
            {"day": "2026-09-15T00:00:00", "created_count": 3, "merged_count": 1},
            {"day": "2026-09-16T00:00:00", "created_count": 0, "merged_count": 2},
        ]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_activity_trend(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, days=30
        )

        assert result.days_analyzed == 30
        assert result.cached is False
        assert len(result.data) == 2
        assert result.data[0].created_count == 3
        assert result.data[1].merged_count == 2
        mock_redis.set.assert_called_once()

    asyncio.run(_run())


def test_analytics_service_cycle_time_trend(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_cycle_time_trend.return_value = [
            {
                "week_start": "2026-09-07T00:00:00",
                "p50_hours": 2.1,
                "p90_hours": 10.5,
                "avg_hours": 3.3,
                "is_partial": False,
            },
            {
                "week_start": "2026-09-14T00:00:00",
                "p50_hours": None,
                "p90_hours": None,
                "avg_hours": None,
                "is_partial": True,
            },
        ]

        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_cycle_time_trend(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, weeks=12
        )

        assert result.weeks_analyzed == 12
        assert result.data[0].p50_hours == 2.1
        # Empty weeks keep None so charts render honest gaps
        assert result.data[1].p50_hours is None
        assert result.data[1].is_partial is True

    asyncio.run(_run())


# ==============================================================================
# New Route Integration Tests
# ==============================================================================


def test_analytics_activity_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    activity_resp = ActivityTrendResponse(
        repository_id=repo_id,
        days_analyzed=30,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        new=AsyncMock(return_value=activity_resp),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/repositories/tracked/{repo_id}/analytics/activity"
        response = client.get(url, params={"days": 30})
        assert response.status_code == 200
        data = response.json()
        assert data["days_analyzed"] == 30
        assert data["cached"] is False


def test_analytics_cycle_time_trend_route(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    trend_resp = CycleTimeTrendResponse(
        repository_id=repo_id,
        weeks_analyzed=12,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        new=AsyncMock(return_value=trend_resp),
    ):
        url = (
            f"/api/v1/workspaces/{workspace_id}"
            f"/repositories/tracked/{repo_id}/analytics/cycle-time-trend"
        )
        response = client.get(url, params={"weeks": 12})
        assert response.status_code == 200
        data = response.json()
        assert data["weeks_analyzed"] == 12


# ==============================================================================
# Phase 2: Workspace Activity & Cycle-Time Trend Route Tests
# ==============================================================================


def test_workspace_activity_route_default_days(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    activity_resp = ActivityTrendResponse(
        workspace_id=workspace_id,
        repository_id=None,
        days_analyzed=30,
        data=[
            ActivityTrendItem(
                day="2026-09-14T00:00:00",
                created_count=12,
                merged_count=8,
            )
        ],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        new=AsyncMock(return_value=activity_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_id)
        assert data["repository_id"] is None
        assert data["days_analyzed"] == 30
        assert len(data["data"]) == 1
        assert data["data"][0]["day"] == "2026-09-14T00:00:00"
        assert data["data"][0]["created_count"] == 12
        assert data["data"][0]["merged_count"] == 8
        assert data["cached"] is False
        mock_get.assert_awaited_once()
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["workspace_id"] == workspace_id
        assert kwargs["repository_id"] is None
        assert kwargs["days"] == 30


def test_workspace_activity_route_custom_days(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    activity_resp = ActivityTrendResponse(
        workspace_id=workspace_id,
        days_analyzed=60,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        new=AsyncMock(return_value=activity_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
        response = client.get(url, params={"days": 60})
        assert response.status_code == 200
        data = response.json()
        assert data["days_analyzed"] == 60
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["days"] == 60


def test_workspace_activity_route_validation_min_days(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
    response = client.get(url, params={"days": 0})
    assert response.status_code == 422


def test_workspace_activity_route_validation_max_days(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
    response = client.get(url, params={"days": 366})
    assert response.status_code == 422


def test_workspace_activity_route_repo_filtering(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    activity_resp = ActivityTrendResponse(
        workspace_id=workspace_id,
        repository_id=repo_id,
        days_analyzed=14,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        new=AsyncMock(return_value=activity_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
        response = client.get(url, params={"days": 14, "repository_id": str(repo_id)})
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_id)
        assert data["repository_id"] == str(repo_id)
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["repository_id"] == repo_id
        assert kwargs["days"] == 14


def test_workspace_activity_route_unknown_repo_404(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        side_effect=RepositoryNotFoundError("Repository not found in this workspace"),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
        response = client.get(url, params={"repository_id": str(repo_id)})
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


def test_workspace_activity_route_unauthorized_403(
    client: TestClient,
    workspace_id: uuid.UUID,
    mock_workspace: Workspace,
) -> None:
    def _raise_forbidden() -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )

    app.dependency_overrides[get_accessible_workspace] = _raise_forbidden
    try:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/activity"
        response = client.get(url)
        assert response.status_code == 403
        assert "You do not have access to this workspace" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace


def test_workspace_cycle_time_route_default_weeks(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    trend_resp = CycleTimeTrendResponse(
        workspace_id=workspace_id,
        repository_id=None,
        weeks_analyzed=12,
        data=[
            CycleTimeTrendItem(
                week_start="2026-09-14T00:00:00",
                p50_hours=24.5,
                p90_hours=72.1,
                avg_hours=35.2,
                is_partial=True,
            )
        ],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        new=AsyncMock(return_value=trend_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_id)
        assert data["repository_id"] is None
        assert data["weeks_analyzed"] == 12
        assert len(data["data"]) == 1
        assert data["data"][0]["week_start"] == "2026-09-14T00:00:00"
        assert data["data"][0]["p50_hours"] == 24.5
        assert data["data"][0]["p90_hours"] == 72.1
        assert data["data"][0]["avg_hours"] == 35.2
        assert data["cached"] is False
        mock_get.assert_awaited_once()
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["workspace_id"] == workspace_id
        assert kwargs["repository_id"] is None
        assert kwargs["weeks"] == 12


def test_workspace_cycle_time_route_custom_weeks(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    trend_resp = CycleTimeTrendResponse(
        workspace_id=workspace_id,
        weeks_analyzed=24,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        new=AsyncMock(return_value=trend_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
        response = client.get(url, params={"weeks": 24})
        assert response.status_code == 200
        data = response.json()
        assert data["weeks_analyzed"] == 24
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["weeks"] == 24


def test_workspace_cycle_time_route_validation_min_weeks(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
    response = client.get(url, params={"weeks": 0})
    assert response.status_code == 422


def test_workspace_cycle_time_route_validation_max_weeks(
    client: TestClient,
    workspace_id: uuid.UUID,
) -> None:
    url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
    response = client.get(url, params={"weeks": 53})
    assert response.status_code == 422


def test_workspace_cycle_time_route_repo_filtering(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    trend_resp = CycleTimeTrendResponse(
        workspace_id=workspace_id,
        repository_id=repo_id,
        weeks_analyzed=8,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        new=AsyncMock(return_value=trend_resp),
    ) as mock_get:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
        response = client.get(url, params={"weeks": 8, "repository_id": str(repo_id)})
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == str(workspace_id)
        assert data["repository_id"] == str(repo_id)
        assert mock_get.await_args is not None
        _, kwargs = mock_get.await_args
        assert kwargs["repository_id"] == repo_id
        assert kwargs["weeks"] == 8


def test_workspace_cycle_time_route_unknown_repo_404(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        side_effect=RepositoryNotFoundError("Repository not found in this workspace"),
    ):
        url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
        response = client.get(url, params={"repository_id": str(repo_id)})
        assert response.status_code == 404
        assert "Repository not found" in response.json()["detail"]


def test_workspace_cycle_time_route_unauthorized_403(
    client: TestClient,
    workspace_id: uuid.UUID,
    mock_workspace: Workspace,
) -> None:
    def _raise_forbidden() -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        )

    app.dependency_overrides[get_accessible_workspace] = _raise_forbidden
    try:
        url = f"/api/v1/workspaces/{workspace_id}/analytics/cycle-time-trend"
        response = client.get(url)
        assert response.status_code == 403
        assert "You do not have access to this workspace" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_accessible_workspace] = lambda: mock_workspace


# ==============================================================================
# Service Scoped Cache and Aggregation Tests
# ==============================================================================


def test_analytics_service_workspace_activity_aggregation(
    workspace_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_daily_activity.return_value = [
            {"day": "2026-09-18T00:00:00", "created_count": 5, "merged_count": 3}
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=AsyncMock(),
            redis=mock_redis,
        )

        result = await service.get_activity_trend(
            mock_db, workspace_id=workspace_id, repository_id=None, days=30
        )

        assert result.workspace_id == workspace_id
        assert result.repository_id is None
        assert result.days_analyzed == 30
        assert len(result.data) == 1
        assert result.data[0].created_count == 5

        expected_cache_key = f"analytics:activity:workspace:{workspace_id}:days:30"
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == expected_cache_key

    asyncio.run(_run())


def test_analytics_service_workspace_activity_repo_filtering(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_daily_activity.return_value = []
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_activity_trend(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, days=14
        )

        assert result.workspace_id == workspace_id
        assert result.repository_id == repo_id
        expected_cache_key = (
            f"analytics:activity:workspace:{workspace_id}:repo:{repo_id}:days:14"
        )
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == expected_cache_key

    asyncio.run(_run())


def test_analytics_service_workspace_cycle_time_aggregation(
    workspace_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_cycle_time_trend.return_value = [
            {
                "week_start": "2026-09-14T00:00:00",
                "p50_hours": 12.0,
                "p90_hours": 36.0,
                "avg_hours": 18.5,
                "is_partial": True,
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=AsyncMock(),
            redis=mock_redis,
        )

        result = await service.get_cycle_time_trend(
            mock_db, workspace_id=workspace_id, repository_id=None, weeks=12
        )

        assert result.workspace_id == workspace_id
        assert result.repository_id is None
        assert result.weeks_analyzed == 12
        assert result.data[0].p50_hours == 12.0

        expected_cache_key = f"analytics:cycletime:workspace:{workspace_id}:weeks:12"
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == expected_cache_key

    asyncio.run(_run())


def test_analytics_service_workspace_cycle_time_repo_filtering(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
    mock_repository: Repository,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_repo_repo.get_by_id.return_value = mock_repository

        mock_analytics_repo = AsyncMock()
        mock_analytics_repo.get_cycle_time_trend.return_value = []
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        service = AnalyticsService(
            analytics_repo=mock_analytics_repo,
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        result = await service.get_cycle_time_trend(
            mock_db, workspace_id=workspace_id, repository_id=repo_id, weeks=8
        )

        assert result.workspace_id == workspace_id
        assert result.repository_id == repo_id
        expected_cache_key = (
            f"analytics:cycletime:workspace:{workspace_id}:repo:{repo_id}:weeks:8"
        )
        mock_redis.set.assert_called_once()
        assert mock_redis.set.call_args[0][0] == expected_cache_key

    asyncio.run(_run())


def test_analytics_service_repo_access_verified_before_cache(
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        other_workspace_repo = Repository(
            workspace_id=uuid.uuid4(),
            github_id=999,
            node_id="R_other",
            name="other-repo",
            full_name="org/other-repo",
            owner_login="org",
            private=False,
            html_url="https://github.com/org/other-repo",
            default_branch="main",
            is_tracked=True,
        )
        other_workspace_repo.id = repo_id
        mock_repo_repo.get_by_id.return_value = other_workspace_repo

        mock_redis = AsyncMock()
        mock_redis.get.return_value = ActivityTrendResponse(
            workspace_id=workspace_id,
            repository_id=repo_id,
            days_analyzed=30,
            data=[],
            cached=True,
        ).model_dump_json()

        service = AnalyticsService(
            analytics_repo=AsyncMock(),
            repository_repo=mock_repo_repo,
            redis=mock_redis,
        )

        with pytest.raises(RepositoryNotFoundError, match="Repository not found in this workspace"):
            await service.get_activity_trend(
                mock_db, workspace_id=workspace_id, repository_id=repo_id, days=30
            )

        with pytest.raises(RepositoryNotFoundError, match="Repository not found in this workspace"):
            await service.get_cycle_time_trend(
                mock_db, workspace_id=workspace_id, repository_id=repo_id, weeks=12
            )

        mock_redis.get.assert_not_called()

    asyncio.run(_run())


# ==============================================================================
# Repository Layer Empty Dataset and Zero-Filling Tests
# ==============================================================================


def test_get_daily_activity_empty_dataset_zero_filled(
    workspace_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        repo = AnalyticsRepository()
        days_result = await repo.get_daily_activity(
            mock_db, workspace_id=workspace_id, days=7
        )

        assert len(days_result) == 7
        for item in days_result:
            assert item["created_count"] == 0
            assert item["merged_count"] == 0
            assert "day" in item

    asyncio.run(_run())


def test_get_cycle_time_trend_empty_dataset_null_metrics(
    workspace_id: uuid.UUID,
) -> None:
    async def _run() -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        repo = AnalyticsRepository()
        trend_result = await repo.get_cycle_time_trend(
            mock_db, workspace_id=workspace_id, weeks=4
        )

        assert len(trend_result) == 4
        for item in trend_result:
            assert item["p50_hours"] is None
            assert item["p90_hours"] is None
            assert item["avg_hours"] is None
            assert "week_start" in item

    asyncio.run(_run())


# ==============================================================================
# Backward Compatibility Verification: Existing Repository-Scoped Routes
# ==============================================================================


def test_existing_repository_activity_route_still_works(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    activity_resp = ActivityTrendResponse(
        workspace_id=workspace_id,
        repository_id=repo_id,
        days_analyzed=30,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_activity_trend",
        new=AsyncMock(return_value=activity_resp),
    ):
        url = (
            f"/api/v1/workspaces/{workspace_id}"
            f"/repositories/tracked/{repo_id}/analytics/activity"
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["repository_id"] == str(repo_id)


def test_existing_repository_cycle_time_route_still_works(
    client: TestClient,
    workspace_id: uuid.UUID,
    repo_id: uuid.UUID,
) -> None:
    trend_resp = CycleTimeTrendResponse(
        workspace_id=workspace_id,
        repository_id=repo_id,
        weeks_analyzed=12,
        data=[],
        cached=False,
    )

    with patch(
        "app.api.v1.analytics.analytics_service.get_cycle_time_trend",
        new=AsyncMock(return_value=trend_resp),
    ):
        url = (
            f"/api/v1/workspaces/{workspace_id}"
            f"/repositories/tracked/{repo_id}/analytics/cycle-time-trend"
        )
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["repository_id"] == str(repo_id)
