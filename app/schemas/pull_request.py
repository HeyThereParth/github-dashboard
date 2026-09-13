"""Pull Request schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PullRequestResponse(BaseModel):
    """Schema for a single pull request mirror."""

    id: uuid.UUID
    repository_id: uuid.UUID
    github_id: int
    node_id: str
    number: int
    title: str
    state: str
    draft: bool
    author_login: str | None = None
    html_url: str
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    github_created_at: datetime
    github_updated_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PullRequestListResponse(BaseModel):
    """Paginated list of pull requests."""

    items: list[PullRequestResponse]
    total: int
    page: int
    per_page: int


class SyncResultResponse(BaseModel):
    """Response returned after synchronizing pull requests from GitHub."""

    repository_id: uuid.UUID
    synced_count: int
    status: str = "completed"
