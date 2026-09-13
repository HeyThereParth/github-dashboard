"""GitHub service — orchestration for GitHub integrations at the workspace level."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.integrations.github.client import GitHubClient, GitHubRepositoryData, github_client
from app.integrations.github.exceptions import GitHubAppConfigError
from app.models.workspace import Workspace
from app.services.workspace_service import WorkspaceService, workspace_service


class GitHubNotConnectedError(Exception):
    """Raised when an operation requires a GitHub connection, but the workspace has none."""


class GitHubService:
    """Business logic connecting workspaces to GitHub data."""

    def __init__(
        self,
        client: GitHubClient = github_client,
        workspaces: WorkspaceService = workspace_service,
        current_settings: Settings = settings,
    ) -> None:
        self._client = client
        self._workspaces = workspaces
        self._settings = current_settings

    def get_install_url(self, workspace_id: uuid.UUID) -> str:
        """Construct the GitHub App installation URL for a workspace."""
        if not self._settings.github_app_slug:
            raise GitHubAppConfigError(
                "GITHUB_APP_SLUG must be configured to generate install URLs"
            )
        return (
            f"https://github.com/apps/{self._settings.github_app_slug}"
            f"/installations/new?state={workspace_id}"
        )

    async def connect_installation(
        self, db: AsyncSession, *, workspace: Workspace, installation_id: int
    ) -> Workspace:
        """Connect an installation ID to a workspace after verifying accessibility."""
        # Verify that GitHub can serve this installation ID before storing it
        await self._client.list_installation_repositories(installation_id, per_page=1)
        return await self._workspaces.set_github_installation(
            db, workspace=workspace, installation_id=installation_id
        )

    async def disconnect_installation(self, db: AsyncSession, *, workspace: Workspace) -> Workspace:
        """Disconnect GitHub from a workspace."""
        return await self._workspaces.set_github_installation(
            db, workspace=workspace, installation_id=None
        )

    async def list_workspace_repositories(
        self, workspace: Workspace, *, page: int = 1, per_page: int = 100
    ) -> list[GitHubRepositoryData]:
        """Fetch repositories for a connected workspace."""
        if workspace.github_installation_id is None:
            raise GitHubNotConnectedError("Workspace is not connected to GitHub")

        return await self._client.list_installation_repositories(
            workspace.github_installation_id, page=page, per_page=per_page
        )


github_service = GitHubService()
