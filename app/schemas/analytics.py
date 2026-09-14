"""Analytics schemas (request/response DTOs)."""

import uuid

from pydantic import BaseModel, Field


class CycleTimeMetrics(BaseModel):
    """Cycle time (time-to-merge) summary in hours."""

    p50_hours: float | None = Field(None, description="Median cycle time in hours")
    p90_hours: float | None = Field(None, description="90th percentile cycle time in hours")
    avg_hours: float | None = Field(None, description="Average cycle time in hours")


class RepositoryMetricsResponse(BaseModel):
    """Aggregated engineering metrics for a repository."""

    repository_id: uuid.UUID
    time_window_days: int | None = Field(
        None, description="Number of days filtered, or None for all time"
    )
    total_prs: int
    open_prs: int
    merged_prs: int
    closed_unmerged_prs: int
    merge_rate_percentage: float | None = Field(None, description="Percentage of closed PRs merged")
    cycle_time: CycleTimeMetrics
    cached: bool = Field(False, description="Whether this response was served from Redis cache")


class WeeklyThroughputItem(BaseModel):
    """Merged PR count for a single week."""

    week_start: str
    merged_count: int


class WeeklyThroughputResponse(BaseModel):
    """Weekly throughput history."""

    repository_id: uuid.UUID
    weeks_analyzed: int
    data: list[WeeklyThroughputItem]
    cached: bool = False


class AuthorMetricsItem(BaseModel):
    """Contributor-level activity and cycle time."""

    author_login: str
    total_prs: int
    merged_prs: int
    avg_cycle_time_hours: float | None = None


class AuthorMetricsResponse(BaseModel):
    """Contributor breakdown."""

    repository_id: uuid.UUID
    time_window_days: int | None = None
    authors: list[AuthorMetricsItem]
    cached: bool = False
