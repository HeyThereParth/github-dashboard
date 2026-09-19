"""Engineering analytics service with resilient cache-aside pattern."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import RedisClient, redis_client
from app.repositories.analytics_repository import (
    AnalyticsRepository,
    analytics_repository,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository,
)
from app.schemas.analytics import (
    ActivityTrendItem,
    ActivityTrendResponse,
    AuthorMetricsItem,
    AuthorMetricsResponse,
    CycleTimeMetrics,
    CycleTimeTrendItem,
    CycleTimeTrendResponse,
    RepositoryMetricsResponse,
    WeeklyThroughputItem,
    WeeklyThroughputResponse,
)
from app.services.repository_service import RepositoryNotFoundError


class AnalyticsService:
    """Orchestrates analytics computations with resilient Redis caching."""

    def __init__(
        self,
        analytics_repo: AnalyticsRepository = analytics_repository,
        repository_repo: RepositoryRepository = repository_repository,
        redis: RedisClient = redis_client,
    ) -> None:
        self._analytics_repo = analytics_repo
        self._repository_repo = repository_repo
        self._redis = redis

    async def _verify_repository_access(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, repository_id: uuid.UUID
    ) -> None:
        """Ensure the repository exists and belongs to the specified workspace."""
        repo = await self._repository_repo.get_by_id(db, repository_id)
        if repo is None or repo.workspace_id != workspace_id:
            raise RepositoryNotFoundError("Repository not found in this workspace")

    async def get_overview_metrics(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        days: int | None = None,
    ) -> RepositoryMetricsResponse:
        """Fetch high-level PR metrics with cache-aside acceleration."""
        await self._verify_repository_access(
            db, workspace_id=workspace_id, repository_id=repository_id
        )

        cache_key = f"analytics:overview:{repository_id}:days:{days}"
        cached_data = await self._redis.get(cache_key)
        if cached_data:
            cached_resp = RepositoryMetricsResponse.model_validate_json(cached_data)
            cached_resp.cached = True
            return cached_resp

        raw_metrics = await self._analytics_repo.get_overview_metrics(
            db, repository_id=repository_id, days=days
        )

        response = RepositoryMetricsResponse(
            repository_id=repository_id,
            time_window_days=days,
            total_prs=raw_metrics["total_prs"],
            open_prs=raw_metrics["open_prs"],
            merged_prs=raw_metrics["merged_prs"],
            closed_unmerged_prs=raw_metrics["closed_unmerged_prs"],
            merge_rate_percentage=raw_metrics["merge_rate_percentage"],
            cycle_time=CycleTimeMetrics(
                p50_hours=raw_metrics["p50_hours"],
                p90_hours=raw_metrics["p90_hours"],
                avg_hours=raw_metrics["avg_hours"],
            ),
            cached=False,
        )

        # Store in Redis with 15-minute TTL (soft-fails gracefully if Redis is offline)
        await self._redis.set(cache_key, response.model_dump_json(), ttl_seconds=900)
        return response

    async def get_weekly_throughput(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        weeks: int = 8,
    ) -> WeeklyThroughputResponse:
        """Fetch weekly merged PR counts with cache-aside acceleration."""
        await self._verify_repository_access(
            db, workspace_id=workspace_id, repository_id=repository_id
        )

        cache_key = f"analytics:throughput:{repository_id}:weeks:{weeks}"
        cached_data = await self._redis.get(cache_key)
        if cached_data:
            cached_resp = WeeklyThroughputResponse.model_validate_json(cached_data)
            cached_resp.cached = True
            return cached_resp

        raw_weeks = await self._analytics_repo.get_weekly_throughput(
            db, repository_id=repository_id, weeks=weeks
        )

        response = WeeklyThroughputResponse(
            repository_id=repository_id,
            weeks_analyzed=weeks,
            data=[WeeklyThroughputItem(**item) for item in raw_weeks],
            cached=False,
        )

        await self._redis.set(cache_key, response.model_dump_json(), ttl_seconds=900)
        return response

    async def get_activity_trend(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID | None = None,
        days: int = 30,
    ) -> ActivityTrendResponse:
        """Fetch daily created-vs-merged PR counts with cache-aside acceleration."""
        if repository_id is not None:
            await self._verify_repository_access(
                db, workspace_id=workspace_id, repository_id=repository_id
            )
            cache_key = (
                f"analytics:activity:workspace:{workspace_id}:repo:{repository_id}:days:{days}"
            )
        else:
            cache_key = f"analytics:activity:workspace:{workspace_id}:days:{days}"

        cached_data = await self._redis.get(cache_key)
        if cached_data:
            cached_resp = ActivityTrendResponse.model_validate_json(cached_data)
            cached_resp.cached = True
            return cached_resp

        raw_days = await self._analytics_repo.get_daily_activity(
            db, repository_id=repository_id, workspace_id=workspace_id, days=days
        )

        response = ActivityTrendResponse(
            workspace_id=workspace_id,
            repository_id=repository_id,
            days_analyzed=days,
            data=[ActivityTrendItem(**item) for item in raw_days],
            cached=False,
        )

        await self._redis.set(cache_key, response.model_dump_json(), ttl_seconds=900)
        return response

    async def get_cycle_time_trend(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID | None = None,
        weeks: int = 12,
    ) -> CycleTimeTrendResponse:
        """Fetch weekly cycle-time percentiles with cache-aside acceleration."""
        if repository_id is not None:
            await self._verify_repository_access(
                db, workspace_id=workspace_id, repository_id=repository_id
            )
            cache_key = (
                f"analytics:cycletime:workspace:{workspace_id}:repo:{repository_id}:weeks:{weeks}"
            )
        else:
            cache_key = f"analytics:cycletime:workspace:{workspace_id}:weeks:{weeks}"

        cached_data = await self._redis.get(cache_key)
        if cached_data:
            cached_resp = CycleTimeTrendResponse.model_validate_json(cached_data)
            cached_resp.cached = True
            return cached_resp

        raw_weeks = await self._analytics_repo.get_cycle_time_trend(
            db, repository_id=repository_id, workspace_id=workspace_id, weeks=weeks
        )

        response = CycleTimeTrendResponse(
            workspace_id=workspace_id,
            repository_id=repository_id,
            weeks_analyzed=weeks,
            data=[CycleTimeTrendItem(**item) for item in raw_weeks],
            cached=False,
        )

        await self._redis.set(cache_key, response.model_dump_json(), ttl_seconds=900)
        return response

    async def get_author_metrics(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        days: int | None = None,
    ) -> AuthorMetricsResponse:
        """Fetch contributor-level metrics with cache-aside acceleration."""
        await self._verify_repository_access(
            db, workspace_id=workspace_id, repository_id=repository_id
        )

        cache_key = f"analytics:authors:{repository_id}:days:{days}"
        cached_data = await self._redis.get(cache_key)
        if cached_data:
            cached_resp = AuthorMetricsResponse.model_validate_json(cached_data)
            cached_resp.cached = True
            return cached_resp

        raw_authors = await self._analytics_repo.get_author_metrics(
            db, repository_id=repository_id, days=days
        )

        response = AuthorMetricsResponse(
            repository_id=repository_id,
            time_window_days=days,
            authors=[AuthorMetricsItem(**item) for item in raw_authors],
            cached=False,
        )

        await self._redis.set(cache_key, response.model_dump_json(), ttl_seconds=900)
        return response

    async def invalidate_repository_cache(self, repository_id: uuid.UUID) -> None:
        """Invalidate all cached metrics for a repository when fresh data arrives."""
        await self._redis.delete_prefix(f"analytics:overview:{repository_id}")
        await self._redis.delete_prefix(f"analytics:throughput:{repository_id}")
        await self._redis.delete_prefix(f"analytics:authors:{repository_id}")
        await self._redis.delete_prefix(f"analytics:activity:{repository_id}")
        await self._redis.delete_prefix(f"analytics:cycletime:{repository_id}")


analytics_service = AnalyticsService()
