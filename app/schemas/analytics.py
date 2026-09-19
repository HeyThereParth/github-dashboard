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
    is_partial: bool = Field(False, description="Whether this week is still in progress")


class ActivityTrendItem(BaseModel):
    """Created vs merged PR counts for a single UTC day."""

    day: str
    created_count: int
    merged_count: int


class ActivityTrendResponse(BaseModel):
    """Daily PR activity history for created-vs-merged trend charts."""

    workspace_id: uuid.UUID | None = None
    repository_id: uuid.UUID | None = None
    days_analyzed: int
    data: list[ActivityTrendItem]
    cached: bool = False


class CycleTimeTrendItem(BaseModel):
    """Cycle-time percentiles for PRs merged in a single week."""

    week_start: str
    p50_hours: float | None = Field(
        None, description="Median cycle time (hours), None if no merges"
    )
    p90_hours: float | None = Field(None, description="90th percentile (hours), None if no merges")
    avg_hours: float | None = Field(None, description="Average (hours), None if no merges")
    is_partial: bool = Field(False, description="Whether this week is still in progress")


class CycleTimeTrendResponse(BaseModel):
    """Weekly cycle-time trend history."""

    workspace_id: uuid.UUID | None = None
    repository_id: uuid.UUID | None = None
    weeks_analyzed: int
    data: list[CycleTimeTrendItem]
    cached: bool = False


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
