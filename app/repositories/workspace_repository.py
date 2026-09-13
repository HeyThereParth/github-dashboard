"""Data access for workspaces and workspace membership."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember


class WorkspaceRepository:
    """Encapsulates all database access for workspaces and membership."""

    async def create(self, db: AsyncSession, *, name: str) -> Workspace:
        workspace = Workspace(name=name)
        db.add(workspace)
        return workspace

    async def get_by_id(self, db: AsyncSession, workspace_id: uuid.UUID) -> Workspace | None:
        return await db.get(Workspace, workspace_id)

    async def list_for_user(self, db: AsyncSession, user_id: uuid.UUID) -> list[Workspace]:
        result = await db.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at)
        )
        return list(result.scalars().unique().all())

    async def add_member(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
    ) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        db.add(member)
        return member

    async def get_membership(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceMember | None:
        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


workspace_repository = WorkspaceRepository()
