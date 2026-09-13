"""Data access repositories.

Repositories own all database access and are the only layer that talks
directly to the database.
"""

from app.repositories.pull_request_repository import (
    PullRequestRepository,
    pull_request_repository,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository,
)
from app.repositories.user_repository import UserRepository, user_repository
from app.repositories.workspace_repository import (
    WorkspaceRepository,
    workspace_repository,
)

__all__ = [
    "PullRequestRepository",
    "RepositoryRepository",
    "UserRepository",
    "WorkspaceRepository",
    "pull_request_repository",
    "repository_repository",
    "user_repository",
    "workspace_repository",
]
