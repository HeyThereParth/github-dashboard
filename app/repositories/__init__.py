"""Data access repositories.

Repositories own all database access and are the only layer that talks
directly to the database.
"""

from app.repositories.analytics_repository import (
    AnalyticsRepository,
    analytics_repository,
)
from app.repositories.pull_request_repository import (
    PullRequestRepository,
    pull_request_repository,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository,
)
from app.repositories.sync_job_repository import (
    SyncJobRepository,
    sync_job_repository,
)
from app.repositories.user_repository import UserRepository, user_repository
from app.repositories.workspace_repository import (
    WorkspaceRepository,
    workspace_repository,
)

__all__ = [
    "AnalyticsRepository",
    "PullRequestRepository",
    "RepositoryRepository",
    "SyncJobRepository",
    "UserRepository",
    "WorkspaceRepository",
    "analytics_repository",
    "pull_request_repository",
    "repository_repository",
    "sync_job_repository",
    "user_repository",
    "workspace_repository",
]
