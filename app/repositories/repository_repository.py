"""Data access layer for repositories."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GitHubRepositoryData
from app.models.repository import Repository


class RepositoryRepository:
    """Encapsulates all database operations for repositories."""

    async def get_by_id(self, db: AsyncSession, repo_id: uuid.UUID) -> Repository | None:
        """Fetch a repository by its internal UUID."""
        return await db.get(Repository, repo_id)

    async def get_by_workspace_and_github_id(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, github_id: int
    ) -> Repository | None:
        """Find a repository in a workspace by its GitHub numeric ID."""
        stmt = select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.github_id == github_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_github_id(
        self, db: AsyncSession, *, github_id: int
    ) -> list[Repository]:
        """Find all tracked repositories mirroring a GitHub repository numeric ID."""
        stmt = select(Repository).where(
            Repository.github_id == github_id,
            Repository.is_tracked.is_(True),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_workspace(
        self, db: AsyncSession, *, workspace_id: uuid.UUID
    ) -> list[Repository]:
        """Return all tracked repositories belonging to a workspace."""
        stmt = (
            select(Repository)
            .where(Repository.workspace_id == workspace_id)
            .order_by(Repository.name)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        repo_data: GitHubRepositoryData,
        owner_login: str,
    ) -> Repository:
        """Idempotently insert or update a repository mirror in the workspace."""
        existing = await self.get_by_workspace_and_github_id(
            db, workspace_id=workspace_id, github_id=repo_data.github_id
        )
        if existing is not None:
            existing.name = repo_data.name
            existing.full_name = repo_data.full_name
            existing.owner_login = owner_login
            existing.private = repo_data.private
            existing.html_url = repo_data.html_url
            existing.default_branch = repo_data.default_branch
            existing.description = repo_data.description
            existing.is_tracked = True
            await db.flush()
            return existing

        repo = Repository(
            workspace_id=workspace_id,
            github_id=repo_data.github_id,
            node_id=repo_data.node_id,
            name=repo_data.name,
            full_name=repo_data.full_name,
            owner_login=owner_login,
            private=repo_data.private,
            html_url=repo_data.html_url,
            default_branch=repo_data.default_branch,
            description=repo_data.description,
            is_tracked=True,
        )
        db.add(repo)
        await db.flush()
        return repo

    async def delete(self, db: AsyncSession, *, repository: Repository) -> None:
        """Remove a repository from the database."""
        await db.delete(repository)
        await db.flush()


repository_repository = RepositoryRepository()
