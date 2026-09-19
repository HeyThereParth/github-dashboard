"""Data access layer for engineering analytics queries."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.repository import Repository


def week_bucket_starts(now: datetime, weeks: int) -> list[datetime]:
    """Return the last ``weeks`` Monday-based week starts (naive UTC, oldest first).

    PostgreSQL ``date_trunc('week', ...)`` truncates to Monday, so these buckets
    align with the SQL aggregation. Naive UTC keeps dict keys comparable with
    bucket values produced via ``timezone('UTC', ...)`` in SQL.
    """
    naive_now = now.astimezone(UTC).replace(tzinfo=None)
    monday = naive_now - timedelta(days=naive_now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return [monday - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]


def day_bucket_starts(now: datetime, days: int) -> list[datetime]:
    """Return the last ``days`` UTC midnight day starts (naive, oldest first)."""
    naive_now = now.astimezone(UTC).replace(tzinfo=None)
    midnight = naive_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return [midnight - timedelta(days=days - 1 - i) for i in range(days)]


def _bucket_key(value: Any) -> datetime | None:
    """Normalize a SQL bucket value to a naive UTC datetime for dict lookup."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def fill_week_counts(counts: dict[datetime, int], starts: list[datetime]) -> list[dict[str, Any]]:
    """Build a zero-filled weekly merged-count series; the newest week is partial."""
    last_index = len(starts) - 1
    return [
        {
            "week_start": start.isoformat(),
            "merged_count": counts.get(start, 0),
            "is_partial": index == last_index,
        }
        for index, start in enumerate(starts)
    ]


def fill_day_counts(
    created: dict[datetime, int],
    merged: dict[datetime, int],
    starts: list[datetime],
) -> list[dict[str, Any]]:
    """Build a zero-filled daily created/merged series."""
    return [
        {
            "day": start.isoformat(),
            "created_count": created.get(start, 0),
            "merged_count": merged.get(start, 0),
        }
        for start in starts
    ]


def fill_week_percentiles(
    rows: dict[datetime, dict[str, Any]], starts: list[datetime]
) -> list[dict[str, Any]]:
    """Build a weekly percentile series; empty weeks keep None values.

    None (instead of zero) is intentional so charts render honest gaps —
    a week with no merged PRs has no measurable cycle time.
    """
    last_index = len(starts) - 1
    return [
        {
            "week_start": start.isoformat(),
            "p50_hours": rows.get(start, {}).get("p50_hours"),
            "p90_hours": rows.get(start, {}).get("p90_hours"),
            "avg_hours": rows.get(start, {}).get("avg_hours"),
            "is_partial": index == last_index,
        }
        for index, start in enumerate(starts)
    ]


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
            func.avg(case((PullRequest.merged_at.is_not(None), duration_hours))).label("avg_hours"),
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
        merge_rate = round((merged_prs / closed_total) * 100.0, 1) if closed_total > 0 else None

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
        """Return zero-filled merged PR counts per week for velocity timelines.

        Buckets are Monday-aligned (matching PostgreSQL ``date_trunc('week')``),
        cover the full requested window with no gaps, and flag the in-progress
        week via ``is_partial`` so charts can de-emphasize it.
        """
        now = datetime.now(UTC)
        starts = week_bucket_starts(now, weeks)
        # timestamptz filter needs an aware datetime; buckets above stay naive.
        first_start = starts[0].replace(tzinfo=UTC)

        week_bucket = func.date_trunc("week", func.timezone("UTC", PullRequest.merged_at)).label(
            "week_start"
        )

        stmt = (
            select(
                week_bucket,
                func.count(PullRequest.id).label("merged_count"),
            )
            .where(
                PullRequest.repository_id == repository_id,
                PullRequest.merged_at.is_not(None),
                PullRequest.merged_at >= first_start,
            )
            .group_by(week_bucket)
            .order_by(week_bucket.asc())
        )

        result = await db.execute(stmt)
        counts: dict[datetime, int] = {}
        for row in result.all():
            key = _bucket_key(row.week_start)
            if key is not None:
                counts[key] = int(row.merged_count)

        return fill_week_counts(counts, starts)

    async def get_daily_activity(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return zero-filled daily created/merged PR counts for activity charts."""
        now = datetime.now(UTC)
        starts = day_bucket_starts(now, days)
        first_start = starts[0].replace(tzinfo=UTC)

        created_bucket = func.date_trunc(
            "day", func.timezone("UTC", PullRequest.github_created_at)
        ).label("day")
        merged_bucket = func.date_trunc("day", func.timezone("UTC", PullRequest.merged_at)).label(
            "day"
        )

        created_stmt = (
            select(
                created_bucket,
                func.count(PullRequest.id).label("pr_count"),
            )
            .where(
                PullRequest.github_created_at >= first_start,
            )
            .group_by(created_bucket)
            .order_by(created_bucket.asc())
        )
        merged_stmt = (
            select(
                merged_bucket,
                func.count(PullRequest.id).label("pr_count"),
            )
            .where(
                PullRequest.merged_at.is_not(None),
                PullRequest.merged_at >= first_start,
            )
            .group_by(merged_bucket)
            .order_by(merged_bucket.asc())
        )

        if repository_id is not None:
            created_stmt = created_stmt.where(PullRequest.repository_id == repository_id)
            merged_stmt = merged_stmt.where(PullRequest.repository_id == repository_id)
        elif workspace_id is not None:
            created_stmt = created_stmt.join(
                Repository, PullRequest.repository_id == Repository.id
            ).where(
                Repository.workspace_id == workspace_id,
                Repository.is_tracked.is_(True),
            )
            merged_stmt = merged_stmt.join(
                Repository, PullRequest.repository_id == Repository.id
            ).where(
                Repository.workspace_id == workspace_id,
                Repository.is_tracked.is_(True),
            )

        created_result = await db.execute(created_stmt)
        merged_result = await db.execute(merged_stmt)

        created_counts: dict[datetime, int] = {}
        for row in created_result.all():
            key = _bucket_key(row.day)
            if key is not None:
                created_counts[key] = int(row.pr_count)

        merged_counts: dict[datetime, int] = {}
        for row in merged_result.all():
            key = _bucket_key(row.day)
            if key is not None:
                merged_counts[key] = int(row.pr_count)

        return fill_day_counts(created_counts, merged_counts, starts)

    async def get_cycle_time_trend(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        weeks: int = 12,
    ) -> list[dict[str, Any]]:
        """Return weekly cycle-time percentiles (bucketed by merge date).

        Weeks with no merged PRs carry None values so charts show gaps honestly
        instead of fabricating a zero cycle time.
        """
        now = datetime.now(UTC)
        starts = week_bucket_starts(now, weeks)
        first_start = starts[0].replace(tzinfo=UTC)

        duration_hours = (
            func.extract("epoch", PullRequest.merged_at - PullRequest.github_created_at) / 3600.0
        )
        week_bucket = func.date_trunc("week", func.timezone("UTC", PullRequest.merged_at)).label(
            "week_start"
        )

        stmt = (
            select(
                week_bucket,
                func.percentile_cont(0.50).within_group(duration_hours).label("p50_hours"),
                func.percentile_cont(0.90).within_group(duration_hours).label("p90_hours"),
                func.avg(duration_hours).label("avg_hours"),
            )
            .where(
                PullRequest.merged_at.is_not(None),
                PullRequest.merged_at >= first_start,
            )
            .group_by(week_bucket)
            .order_by(week_bucket.asc())
        )

        if repository_id is not None:
            stmt = stmt.where(PullRequest.repository_id == repository_id)
        elif workspace_id is not None:
            stmt = stmt.join(Repository, PullRequest.repository_id == Repository.id).where(
                Repository.workspace_id == workspace_id,
                Repository.is_tracked.is_(True),
            )

        result = await db.execute(stmt)
        rows: dict[datetime, dict[str, Any]] = {}
        for row in result.all():
            key = _bucket_key(row.week_start)
            if key is None:
                continue
            rows[key] = {
                "p50_hours": round(float(row.p50_hours), 2) if row.p50_hours is not None else None,
                "p90_hours": round(float(row.p90_hours), 2) if row.p90_hours is not None else None,
                "avg_hours": round(float(row.avg_hours), 2) if row.avg_hours is not None else None,
            }

        return fill_week_percentiles(rows, starts)

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

        stmt = select(
            PullRequest.author_login,
            func.count(PullRequest.id).label("total_prs"),
            func.count(case((PullRequest.merged_at.is_not(None), 1))).label("merged_prs"),
            func.avg(case((PullRequest.merged_at.is_not(None), duration_hours))).label(
                "avg_cycle_time_hours"
            ),
        ).where(
            PullRequest.repository_id == repository_id,
            PullRequest.author_login.is_not(None),
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
