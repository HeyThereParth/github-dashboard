"""Data access layer for engineering analytics queries."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest


class AnalyticsRepository:
    """Computes statistical aggregations on pull requests directly in PostgreSQL."""

    async def get_overview_metrics(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        days: int | None = None,
    ) -> dict[str, Any]:
        """Compute cycle time percentiles and throughput totals for a repository."""
        duration_seconds = func.extract(
            "epoch", PullRequest.merged_at - PullRequest.github_created_at
        )
        duration_hours = duration_seconds / 3600.0

        stmt = select(
            func.count(PullRequest.id).label("total_prs"),
            func.count(case((PullRequest.state == "open", 1))).label("open_prs"),
            func.count(case((PullRequest.merged_at.is_not(None), 1))).label("merged_prs"),
            func.count(
                case(
                    (
                        (PullRequest.state == "closed") & (PullRequest.merged_at.is_(None)),
                        1,
                    )
                )
            ).label("closed_unmerged_prs"),
            func.percentile_cont(0.50).within_group(duration_hours).label("p50_hours"),
            func.percentile_cont(0.90).within_group(duration_hours).label("p90_hours"),
            func.avg(case((PullRequest.merged_at.is_not(None), duration_hours))).label(
                "avg_hours"
            ),
        ).where(PullRequest.repository_id == repository_id)

        if days is not None:
            since = datetime.now(UTC) - timedelta(days=days)
            stmt = stmt.where(PullRequest.github_created_at >= since)

        result = await db.execute(stmt)
        row = result.one()

        total_prs: int = row.total_prs or 0
        open_prs: int = row.open_prs or 0
        merged_prs: int = row.merged_prs or 0
        closed_unmerged_prs: int = row.closed_unmerged_prs or 0

        p50_hours: float | None = (
            round(float(row.p50_hours), 2) if row.p50_hours is not None else None
        )
        p90_hours: float | None = (
            round(float(row.p90_hours), 2) if row.p90_hours is not None else None
        )
        avg_hours: float | None = (
            round(float(row.avg_hours), 2) if row.avg_hours is not None else None
        )

        closed_total = merged_prs + closed_unmerged_prs
        merge_rate = (
            round((merged_prs / closed_total) * 100.0, 1) if closed_total > 0 else None
        )

        return {
            "total_prs": total_prs,
            "open_prs": open_prs,
            "merged_prs": merged_prs,
            "closed_unmerged_prs": closed_unmerged_prs,
            "merge_rate_percentage": merge_rate,
            "p50_hours": p50_hours,
            "p90_hours": p90_hours,
            "avg_hours": avg_hours,
        }

    async def get_weekly_throughput(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        weeks: int = 8,
    ) -> list[dict[str, Any]]:
        """Return merged PR counts grouped by week for velocity timelines."""
        since = datetime.now(UTC) - timedelta(weeks=weeks)
        week_bucket = func.date_trunc("week", PullRequest.merged_at).label("week_start")

        stmt = (
            select(
                week_bucket,
                func.count(PullRequest.id).label("merged_count"),
            )
            .where(
                PullRequest.repository_id == repository_id,
                PullRequest.merged_at.is_not(None),
                PullRequest.merged_at >= since,
            )
            .group_by(week_bucket)
            .order_by(week_bucket.asc())
        )

        result = await db.execute(stmt)
        return [
            {
                "week_start": (
                    row.week_start.isoformat()
                    if hasattr(row.week_start, "isoformat")
                    else str(row.week_start)
                ),
                "merged_count": int(row.merged_count),
            }
            for row in result.all()
        ]

    async def get_author_metrics(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        days: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return contributor activity and average cycle time."""
        duration_hours = (
            func.extract("epoch", PullRequest.merged_at - PullRequest.github_created_at) / 3600.0
        )

        stmt = (
            select(
                PullRequest.author_login,
                func.count(PullRequest.id).label("total_prs"),
                func.count(case((PullRequest.merged_at.is_not(None), 1))).label("merged_prs"),
                func.avg(case((PullRequest.merged_at.is_not(None), duration_hours))).label(
                    "avg_cycle_time_hours"
                ),
            )
            .where(
                PullRequest.repository_id == repository_id,
                PullRequest.author_login.is_not(None),
            )
        )

        if days is not None:
            since = datetime.now(UTC) - timedelta(days=days)
            stmt = stmt.where(PullRequest.github_created_at >= since)

        stmt = (
            stmt.group_by(PullRequest.author_login)
            .order_by(func.count(PullRequest.id).desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        return [
            {
                "author_login": str(row.author_login),
                "total_prs": int(row.total_prs),
                "merged_prs": int(row.merged_prs),
                "avg_cycle_time_hours": round(float(row.avg_cycle_time_hours), 2)
                if row.avg_cycle_time_hours is not None
                else None,
            }
            for row in result.all()
        ]


analytics_repository = AnalyticsRepository()
