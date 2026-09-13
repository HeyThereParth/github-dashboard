import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_accessible_workspace, get_current_user, get_owned_workspace
from app.core.database import get_db
from app.integrations.github.exceptions import (
    GitHubAppConfigError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.github import (
    GitHubConnectRequest,
    GitHubInstallUrlResponse,
    GitHubRepositoryResponse,
)
from app.schemas.repository import (
    RepositoryResponse,
    RepositorySummary,
    RepositoryTrackRequest,
)
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceSummary
from app.services.github_service import GitHubNotConnectedError, github_service
from app.services.repository_service import RepositoryNotFoundError, repository_service
from app.services.workspace_service import workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    workspace = await workspace_service.create_workspace(
        db, user_id=current_user.id, name=payload.name
    )
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceSummary])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceSummary]:
    workspaces = await workspace_service.list_workspaces(db, user_id=current_user.id)
    return [WorkspaceSummary.model_validate(workspace) for workspace in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace: Workspace = Depends(get_accessible_workspace),
) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(workspace)


@router.get("/{workspace_id}/github/install-url", response_model=GitHubInstallUrlResponse)
async def get_github_install_url(
    workspace: Workspace = Depends(get_owned_workspace),
) -> GitHubInstallUrlResponse:
    """Generate the installation URL to connect the GitHub App to this workspace (Owner only)."""
    try:
        url = github_service.get_install_url(workspace.id)
        return GitHubInstallUrlResponse(install_url=url)
    except GitHubAppConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub App is not configured on the server",
        ) from exc


@router.post("/{workspace_id}/github/connect", response_model=WorkspaceResponse)
async def connect_github_installation(
    payload: GitHubConnectRequest,
    workspace: Workspace = Depends(get_owned_workspace),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Link a GitHub App installation to this workspace (Owner only)."""
    try:
        updated = await github_service.connect_installation(
            db, workspace=workspace, installation_id=payload.installation_id
        )
        return WorkspaceResponse.model_validate(updated)
    except (GitHubAuthError, GitHubNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to verify GitHub installation: {exc}",
        ) from exc


@router.delete("/{workspace_id}/github/disconnect", response_model=WorkspaceResponse)
async def disconnect_github_installation(
    workspace: Workspace = Depends(get_owned_workspace),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceResponse:
    """Disconnect GitHub from this workspace (Owner only)."""
    updated = await github_service.disconnect_installation(db, workspace=workspace)
    return WorkspaceResponse.model_validate(updated)


@router.get(
    "/{workspace_id}/github/repositories",
    response_model=list[GitHubRepositoryResponse],
)
async def list_workspace_github_repositories(
    workspace: Workspace = Depends(get_accessible_workspace),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=100),
) -> list[GitHubRepositoryResponse]:
    """List all GitHub repositories accessible via the connected installation (Any member)."""
    try:
        repos = await github_service.list_workspace_repositories(
            workspace, page=page, per_page=per_page
        )
        return [
            GitHubRepositoryResponse(
                github_id=r.github_id,
                node_id=r.node_id,
                name=r.name,
                full_name=r.full_name,
                private=r.private,
                html_url=r.html_url,
                default_branch=r.default_branch,
                description=r.description,
            )
            for r in repos
        ]
    except GitHubNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"GitHub rate limit exceeded. Resets at: {exc.reset_at}",
        ) from exc
    except GitHubAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub authentication error: {exc}",
        ) from exc


@router.post(
    "/{workspace_id}/repositories/track",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def track_repository(
    payload: RepositoryTrackRequest,
    workspace: Workspace = Depends(get_owned_workspace),
    db: AsyncSession = Depends(get_db),
) -> RepositoryResponse:
    """Add a GitHub repository to tracking in this workspace (Owner only)."""
    try:
        repo = await repository_service.track_repository(
            db, workspace=workspace, owner=payload.owner, repo=payload.repo
        )
        return RepositoryResponse.model_validate(repo)
    except GitHubNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GitHubNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub repository {payload.owner}/{payload.repo} not found",
        ) from exc
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"GitHub rate limit exceeded. Resets at: {exc.reset_at}",
        ) from exc
    except GitHubAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub authentication error: {exc}",
        ) from exc


@router.get(
    "/{workspace_id}/repositories/tracked",
    response_model=list[RepositorySummary],
)
async def list_tracked_repositories(
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[RepositorySummary]:
    """List all tracked repositories stored in this workspace (Any member)."""
    repos = await repository_service.list_tracked_repositories(db, workspace_id=workspace.id)
    return [RepositorySummary.model_validate(r) for r in repos]


@router.get(
    "/{workspace_id}/repositories/tracked/{repository_id}",
    response_model=RepositoryResponse,
)
async def get_tracked_repository(
    repository_id: uuid.UUID,
    workspace: Workspace = Depends(get_accessible_workspace),
    db: AsyncSession = Depends(get_db),
) -> RepositoryResponse:
    """Get details of a tracked repository (Any member)."""
    try:
        repo = await repository_service.get_tracked_repository(
            db, workspace_id=workspace.id, repository_id=repository_id
        )
        return RepositoryResponse.model_validate(repo)
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{workspace_id}/repositories/tracked/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def untrack_repository(
    repository_id: uuid.UUID,
    workspace: Workspace = Depends(get_owned_workspace),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a repository from tracking (Owner only)."""
    try:
        await repository_service.untrack_repository(
            db, workspace_id=workspace.id, repository_id=repository_id
        )
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
