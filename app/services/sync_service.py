"""Pull request synchronization service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GitHubClient, github_client
from app.repositories.pull_request_repository import (
    PullRequestRepository,
    pull_request_repository,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository,
)
from app.repositories.workspace_repository import (
    WorkspaceRepository,
    workspace_repository,
)
from app.schemas.pull_request import (
    PullRequestListResponse,
    PullRequestResponse,
    SyncResultResponse,
)
from app.services.github_service import GitHubNotConnectedError
from app.services.repository_service import RepositoryNotFoundError


class RepositoryNotTrackedError(Exception):
    """Raised when trying to sync a repository that is not marked as tracked."""


class WorkspaceNotFoundError(Exception):
    """Raised when the specified workspace does not exist."""


class SyncService:
    """Orchestrates pulling data from GitHub and persisting it to Neon PostgreSQL."""

    def __init__(
        self,
        pull_request_repo: PullRequestRepository = pull_request_repository,
        repository_repo: RepositoryRepository = repository_repository,
        workspace_repo: WorkspaceRepository = workspace_repository,
        client: GitHubClient = github_client,
    ) -> None:
        self._pull_request_repo = pull_request_repo
        self._repository_repo = repository_repo
        self._workspace_repo = workspace_repo
        self._client = client

    async def sync_repository_pull_requests(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
    ) -> SyncResultResponse:
        """Fetch all pull requests from GitHub and idempotently upsert them into the database."""
        # 1. Validate repository belongs to this workspace
        repo = await self._repository_repo.get_by_id(db, repository_id)
        if repo is None or repo.workspace_id != workspace_id:
            raise RepositoryNotFoundError("Repository not found in this workspace")

        if not repo.is_tracked:
            raise RepositoryNotTrackedError("Cannot sync a repository that is not tracked")

        # 2. Validate workspace GitHub connection
        workspace = await self._workspace_repo.get_by_id(db, workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError("Workspace not found")

        if workspace.github_installation_id is None:
            raise GitHubNotConnectedError("Workspace is not connected to GitHub")

        # 3. Pull all PRs from GitHub API across pages
        prs_data = await self._client.fetch_all_pull_requests(
            workspace.github_installation_id,
            owner=repo.owner_login,
            repo=repo.name,
            state="all",
        )

        # 4. Atomically upsert into database
        synced_count = await self._pull_request_repo.upsert_batch(
            db,
            repository_id=repo.id,
            pull_requests=prs_data,
        )

        return SyncResultResponse(
            repository_id=repo.id,
            synced_count=synced_count,
            status="completed",
        )

    async def list_repository_pull_requests(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
        state: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> PullRequestListResponse:
        """Fetch a paginated list of pull requests for a tracked repository."""
        repo = await self._repository_repo.get_by_id(db, repository_id)
        if repo is None or repo.workspace_id != workspace_id:
            raise RepositoryNotFoundError("Repository not found in this workspace")

        offset = (page - 1) * per_page
        prs = await self._pull_request_repo.list_by_repository(
            db,
            repository_id=repo.id,
            state=state,
            limit=per_page,
            offset=offset,
        )
        total = await self._pull_request_repo.count_by_repository(
            db, repository_id=repo.id, state=state
        )

        items = [PullRequestResponse.model_validate(pr) for pr in prs]
        return PullRequestListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )


sync_service = SyncService()
