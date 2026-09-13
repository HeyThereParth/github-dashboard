"""Workspace API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    """Request body for creating a workspace."""

    name: str = Field(min_length=1, max_length=255)


class WorkspaceSummary(BaseModel):
    """Lightweight representation used in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class WorkspaceResponse(BaseModel):
    """Full representation returned on create and detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
