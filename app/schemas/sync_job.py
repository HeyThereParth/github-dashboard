"""SyncJob schemas (request/response DTOs)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SyncJobCreateResponse(BaseModel):
    """Response returned when a sync job is accepted for background execution."""

    job_id: uuid.UUID = Field(..., description="Unique ID for tracking job progress")
    status: str = Field("queued", description="Initial job status")
    message: str = Field(
        "Synchronization task enqueued successfully",
        description="Human-readable status confirmation",
    )


class SyncJobResponse(BaseModel):
    """Complete detail of a background sync job."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    repository_id: uuid.UUID
    status: str
    total_synced: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def job_id(self) -> uuid.UUID:
        """Alias for id so frontend polling contracts reading job_id or id both succeed."""
        return self.id

    model_config = ConfigDict(from_attributes=True)
