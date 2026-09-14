"""Data access layer for sync jobs."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_job import SyncJob


class SyncJobRepository:
    """Encapsulates database operations for sync jobs."""

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        status: str = "queued",
    ) -> SyncJob:
        """Create a new background sync job record."""
        job = SyncJob(
            workspace_id=workspace_id,
            repository_id=repository_id,
            status=status,
            total_synced=0,
        )
        db.add(job)
        await db.flush()
        return job

    async def get_by_id(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
    ) -> SyncJob | None:
        """Retrieve a sync job by its primary key UUID."""
        return await db.get(SyncJob, job_id)

    async def list_for_repository(
        self,
        db: AsyncSession,
        *,
        repository_id: uuid.UUID,
        limit: int = 10,
    ) -> Sequence[SyncJob]:
        """Fetch recent sync jobs for a repository."""
        stmt = (
            select(SyncJob)
            .where(SyncJob.repository_id == repository_id)
            .order_by(desc(SyncJob.created_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def mark_processing(
        self,
        db: AsyncSession,
        *,
        job: SyncJob,
    ) -> SyncJob:
        """Transition job status to processing."""
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        await db.flush()
        return job

    async def mark_completed(
        self,
        db: AsyncSession,
        *,
        job: SyncJob,
        total_synced: int,
    ) -> SyncJob:
        """Transition job status to completed."""
        job.status = "completed"
        job.total_synced = total_synced
        job.completed_at = datetime.now(UTC)
        await db.flush()
        return job

    async def mark_failed(
        self,
        db: AsyncSession,
        *,
        job: SyncJob,
        error_message: str,
    ) -> SyncJob:
        """Transition job status to failed with error details."""
        job.status = "failed"
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        await db.flush()
        return job


sync_job_repository = SyncJobRepository()
