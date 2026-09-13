"""Workspace (tenant) API routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_accessible_workspace, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse, WorkspaceSummary
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
