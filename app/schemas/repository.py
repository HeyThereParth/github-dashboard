"""Repository API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryTrackRequest(BaseModel):
    """Request body for tracking a GitHub repository in a workspace."""

    owner: str = Field(min_length=1, max_length=255, description="Repository owner or organization")
    repo: str = Field(min_length=1, max_length=255, description="Repository name")


class RepositorySummary(BaseModel):
    """Lightweight representation of a tracked repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    full_name: str
    private: bool
    is_tracked: bool
    html_url: str
    default_branch: str


class RepositoryResponse(BaseModel):
    """Full representation of a tracked repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    github_id: int
    node_id: str
    name: str
    full_name: str
    owner_login: str
    private: bool
    html_url: str
    default_branch: str
    description: str | None = None
    is_tracked: bool
    created_at: datetime
    updated_at: datetime
