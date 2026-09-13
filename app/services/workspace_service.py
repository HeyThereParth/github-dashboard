"""Workspace and membership business logic."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceRole
from app.repositories.workspace_repository import WorkspaceRepository, workspace_repository


class WorkspaceNotFoundError(Exception):
    """Raised when a workspace does not exist."""


class WorkspaceForbiddenError(Exception):
    """Raised when the authenticated user is not a member of the workspace."""


class WorkspaceService:
    """Business logic for workspaces and tenant authorization."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def create_workspace(
        self, db: AsyncSession, *, user_id: uuid.UUID, name: str
    ) -> Workspace:
        """Create a workspace and add ``user_id`` as its owner, atomically.

        Both inserts share the same transaction (committed by the request-scoped
        session dependency), so a workspace can never exist without its owner.
        """
        workspace = await self._repository.create(db, name=name)
        await db.flush()  # assign workspace.id within the transaction
        await self._repository.add_member(
            db, workspace_id=workspace.id, user_id=user_id, role=WorkspaceRole.OWNER.value
        )
        return workspace

    async def list_workspaces(self, db: AsyncSession, *, user_id: uuid.UUID) -> list[Workspace]:
        return await self._repository.list_for_user(db, user_id)

    async def get_workspace_for_member(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> Workspace:
        """Return the workspace if ``user_id`` is a member, otherwise raise.

        Raises ``WorkspaceNotFoundError`` when the workspace does not exist and
        ``WorkspaceForbiddenError`` when it exists but the user is not a member.
        """
        workspace = await self._repository.get_by_id(db, workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError()

        membership = await self._repository.get_membership(
            db, workspace_id=workspace_id, user_id=user_id
        )
        if membership is None:
            raise WorkspaceForbiddenError()

        return workspace


workspace_service = WorkspaceService(workspace_repository)
