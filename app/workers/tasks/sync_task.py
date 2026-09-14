"""Background task to synchronize pull requests for a repository."""

import logging
import uuid

from app.core.database import async_session_factory
from app.repositories.sync_job_repository import (
    SyncJobRepository,
    sync_job_repository,
)
from app.services.sync_service import SyncService, sync_service

logger = logging.getLogger(__name__)


async def run_sync_job(
    *,
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    repository_id: uuid.UUID,
    job_repo: SyncJobRepository = sync_job_repository,
    service: SyncService = sync_service,
) -> None:
    """Execute a background synchronization task and update its database status."""
    logger.info("Starting background sync job %s for repository %s", job_id, repository_id)

    async with async_session_factory() as db:
        job = await job_repo.get_by_id(db, job_id)
        if job is None:
            logger.error("SyncJob %s not found in database; aborting", job_id)
            return

        await job_repo.mark_processing(db, job=job)
        await db.commit()

        try:
            result = await service.sync_repository_pull_requests(
                db, workspace_id=workspace_id, repository_id=repository_id
            )
            await job_repo.mark_completed(db, job=job, total_synced=result.synced_count)
            await db.commit()
            logger.info(
                "SyncJob %s completed successfully: %d PRs synced",
                job_id,
                result.synced_count,
            )
        except Exception as exc:
            await db.rollback()
            logger.exception("SyncJob %s failed: %s", job_id, exc)
            refreshed = await job_repo.get_by_id(db, job_id)
            if refreshed:
                await job_repo.mark_failed(db, job=refreshed, error_message=str(exc))
                await db.commit()
