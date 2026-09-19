"""Analytics API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_accessible_workspace
from app.core.database import get_db
from app.models.workspace import Workspace
from app.schemas.analytics import (
    ActivityTrendResponse,
    AuthorMetricsResponse,
    CycleTimeTrendResponse,
    RepositoryMetricsResponse,
    WeeklyThroughputResponse,
)
from app.services.analytics_service import analytics_service
from app.services.repository_service import RepositoryNotFoundError

router = APIRouter(
    prefix="/workspaces/{workspace_id}/repositories/tracked/{repository_id}/analytics",
    tags=["analytics"],
)


@router.get(
    "/overview",
    response_model=RepositoryMetricsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_repository_overview_metrics(
    repository_id: uuid.UUID,
    days: int | None = Query(
        30,
        ge=1,
        le=365,
        description="Filter by past N days (e.g. 7, 30, 90), or pass null for all time",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> RepositoryMetricsResponse:
    """Fetch aggregated engineering metrics (Cycle Time p50/p90, merge rates, volume)."""
    try:
        return await analytics_service.get_overview_metrics(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            days=days,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/throughput",
    response_model=WeeklyThroughputResponse,
    status_code=status.HTTP_200_OK,
)
async def get_weekly_throughput_metrics(
    repository_id: uuid.UUID,
    weeks: int = Query(
        8,
        ge=1,
        le=52,
        description="Number of past weeks to analyze",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> WeeklyThroughputResponse:
    """Fetch weekly merged PR throughput history for velocity charts."""
    try:
        return await analytics_service.get_weekly_throughput(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            weeks=weeks,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/activity",
    response_model=ActivityTrendResponse,
    status_code=status.HTTP_200_OK,
)
async def get_activity_trend_metrics(
    repository_id: uuid.UUID,
    days: int = Query(
        30,
        ge=1,
        le=365,
        description="Number of past days to analyze",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> ActivityTrendResponse:
    """Fetch daily created-vs-merged PR counts for activity trend charts."""
    try:
        return await analytics_service.get_activity_trend(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            days=days,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/cycle-time-trend",
    response_model=CycleTimeTrendResponse,
    status_code=status.HTTP_200_OK,
)
async def get_cycle_time_trend_metrics(
    repository_id: uuid.UUID,
    weeks: int = Query(
        12,
        ge=1,
        le=52,
        description="Number of past weeks to analyze",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> CycleTimeTrendResponse:
    """Fetch weekly cycle-time percentiles for engineering-pace trend charts."""
    try:
        return await analytics_service.get_cycle_time_trend(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            weeks=weeks,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/authors",
    response_model=AuthorMetricsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_author_metrics(
    repository_id: uuid.UUID,
    days: int | None = Query(
        30,
        ge=1,
        le=365,
        description="Filter by past N days, or pass null for all time",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> AuthorMetricsResponse:
    """Fetch contributor-level pull request activity and cycle times."""
    try:
        return await analytics_service.get_author_metrics(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            days=days,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


workspace_router = APIRouter(
    prefix="/workspaces/{workspace_id}/analytics",
    tags=["analytics"],
)


@workspace_router.get(
    "/activity",
    response_model=ActivityTrendResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workspace_activity_trend(
    days: int = Query(
        30,
        ge=1,
        le=365,
        description="Number of past days to analyze",
    ),
    repository_id: uuid.UUID | None = Query(
        None,
        description="Optional repository ID to filter by",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> ActivityTrendResponse:
    """Fetch daily created-vs-merged PR counts for workspace or specific repository."""
    try:
        return await analytics_service.get_activity_trend(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            days=days,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@workspace_router.get(
    "/cycle-time-trend",
    response_model=CycleTimeTrendResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workspace_cycle_time_trend(
    weeks: int = Query(
        12,
        ge=1,
        le=52,
        description="Number of past weeks to analyze",
    ),
    repository_id: uuid.UUID | None = Query(
        None,
        description="Optional repository ID to filter by",
    ),
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> CycleTimeTrendResponse:
    """Fetch weekly cycle-time percentiles for workspace or specific repository."""
    try:
        return await analytics_service.get_cycle_time_trend(
            db,
            workspace_id=workspace.id,
            repository_id=repository_id,
            weeks=weeks,
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
