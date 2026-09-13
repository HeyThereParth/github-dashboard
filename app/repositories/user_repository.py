"""Data access for users."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Encapsulates all database access for the ``users`` table."""

    async def get_by_auth_provider_user_id(
        self, db: AsyncSession, auth_provider_user_id: str
    ) -> User | None:
        result = await db.execute(
            select(User).where(User.auth_provider_user_id == auth_provider_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, user_id: uuid.UUID) -> User | None:
        return await db.get(User, user_id)

    async def create(
        self,
        db: AsyncSession,
        *,
        auth_provider_user_id: str,
        email: str | None,
        name: str | None,
        avatar_url: str | None,
    ) -> User:
        user = User(
            auth_provider_user_id=auth_provider_user_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
        )
        db.add(user)
        return user


user_repository = UserRepository()
