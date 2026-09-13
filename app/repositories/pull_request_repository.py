"""Data access layer for pull requests."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GitHubPullRequestData
from app.models.pull_request import PullRequest


class PullRequestRepository:
    """Encapsulates all database operations for pull requests."""

    async def get_by_id(self, db: AsyncSession, pr_id: uuid.UUID) -> PullRequest | None:
        """Fetch a pull request by its primary UUID."""
        return await db.get(PullRequest, pr_id)

    async def get_by_number(
        self, db: AsyncSession, *, repository_id: uuid.UUID, number: int
    ) -> PullRequest | None:
        """Fetch a pull request by repository ID and PR number."""
        stmt = select(PullRequest).where(
            PullRequest.repository_id == repository_id,
            PullRequest.number == number,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_repository(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[PullRequest]:
        """Fetch a paginated list of pull requests for a repository."""
        stmt = (
            select(PullRequest)
            .where(PullRequest.repository_id == repository_id)
            .order_by(PullRequest.number.desc())
            .limit(limit)
            .offset(offset)
        )
        if state is not None and state != "all":
            stmt = stmt.where(PullRequest.state == state)

        result = await db.execute(stmt)
        return result.scalars().all()

    async def count_by_repository(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        state: str | None = None,
    ) -> int:
        """Count total pull requests for a repository."""
        stmt = (
            select(func.count(PullRequest.id))
            .where(PullRequest.repository_id == repository_id)
        )
        if state is not None and state != "all":
            stmt = stmt.where(PullRequest.state == state)

        result = await db.execute(stmt)
        return result.scalar_one() or 0

    async def upsert_batch(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        pull_requests: list[GitHubPullRequestData],
    ) -> int:
        """Atomically upsert a batch of pull requests using PostgreSQL ON CONFLICT.

        Returns the count of upserted records.
        """
        if not pull_requests:
            return 0

        # Build values dictionary for each PR
        records = [
            {
                "id": uuid.uuid4(),
                "repository_id": repository_id,
                "github_id": pr.github_id,
                "node_id": pr.node_id,
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "draft": pr.draft,
                "author_login": pr.author_login,
                "html_url": pr.html_url,
                "merged_at": pr.merged_at,
                "closed_at": pr.closed_at,
                "github_created_at": pr.github_created_at,
                "github_updated_at": pr.github_updated_at,
            }
            for pr in pull_requests
        ]

        stmt = pg_insert(PullRequest).values(records)
        upsert_stmt = stmt.on_conflict_do_update(
            constraint="uq_pull_requests_repo_number",
            set_={
                "title": stmt.excluded.title,
                "state": stmt.excluded.state,
                "draft": stmt.excluded.draft,
                "author_login": stmt.excluded.author_login,
                "html_url": stmt.excluded.html_url,
                "merged_at": stmt.excluded.merged_at,
                "closed_at": stmt.excluded.closed_at,
                "github_updated_at": stmt.excluded.github_updated_at,
                "updated_at": func.now(),
            },
        )

        await db.execute(upsert_stmt)
        await db.flush()
        return len(records)


pull_request_repository = PullRequestRepository()
