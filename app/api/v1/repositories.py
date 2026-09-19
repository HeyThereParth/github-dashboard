"""Repository API routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_accessible_workspace, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.repositories.sync_job_repository import sync_job_repository
from app.schemas.sync_job import SyncJobResponse

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get(
    "/sync-jobs/{job_id}",
    response_model=SyncJobResponse,
    status_code=status.HTTP_200_OK,
)
async def get_sync_job_by_id(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SyncJobResponse:
    """Get status and details for a sync job directly by job ID.

    Verifies the job exists and confirms tenant authorization (the current
    user must have member or owner access to the workspace that owns the job).
    """
    job = await sync_job_repository.get_by_id(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sync job not found",
        )

    # Protect tenant boundary: user must be an authorized member of the job's workspace
    await get_accessible_workspace(
        workspace_id=job.workspace_id,
        db=db,
        current_user=current_user,
    )

    return SyncJobResponse.model_validate(job)
