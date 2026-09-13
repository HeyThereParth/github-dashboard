"""Repository business logic service."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GitHubClient, github_client
from app.models.repository import Repository
from app.models.workspace import Workspace
from app.repositories.repository_repository import RepositoryRepository, repository_repository
from app.services.github_service import GitHubNotConnectedError


class RepositoryNotFoundError(Exception):
    """Raised when a repository is not found in the workspace."""


class RepositoryService:
    """Business logic for tracking and managing repositories within workspaces."""

    def __init__(
        self,
        repository: RepositoryRepository = repository_repository,
        client: GitHubClient = github_client,
    ) -> None:
        self._repository = repository
        self._client = client

    async def track_repository(
        self,
        db: AsyncSession,
        *,
        workspace: Workspace,
        owner: str,
        repo: str,
    ) -> Repository:
        """Fetch repository details from GitHub and save it as a tracked repository in Neon DB."""
        if workspace.github_installation_id is None:
            raise GitHubNotConnectedError("Workspace is not connected to GitHub")

        repo_data = await self._client.get_repository(
            workspace.github_installation_id, owner=owner, repo=repo
        )

        return await self._repository.upsert(
            db,
            workspace_id=workspace.id,
            repo_data=repo_data,
            owner_login=owner,
        )

    async def list_tracked_repositories(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
    ) -> list[Repository]:
        """Return all tracked repositories in the workspace."""
        return await self._repository.list_for_workspace(db, workspace_id=workspace_id)

    async def get_tracked_repository(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
    ) -> Repository:
        """Return a single tracked repository, ensuring it belongs to the given workspace."""
        repo = await self._repository.get_by_id(db, repository_id)
        if repo is None or repo.workspace_id != workspace_id:
            raise RepositoryNotFoundError("Repository not found in this workspace")
        return repo

    async def untrack_repository(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
    ) -> None:
        """Remove a repository from tracking."""
        repo = await self.get_tracked_repository(
            db, workspace_id=workspace_id, repository_id=repository_id
        )
        await self._repository.delete(db, repository=repo)


repository_service = RepositoryService()
