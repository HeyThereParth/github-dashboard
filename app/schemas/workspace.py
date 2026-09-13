"""Workspace API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class WorkspaceCreate(BaseModel):
    """Request body for creating a workspace."""

    name: str = Field(min_length=1, max_length=255)


class WorkspaceSummary(BaseModel):
    """Lightweight representation used in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    github_installation_id: int | None = None
    created_at: datetime


class WorkspaceResponse(BaseModel):
    """Full representation returned on create and detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    github_installation_id: int | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_github_connected(self) -> bool:
        return self.github_installation_id is not None
