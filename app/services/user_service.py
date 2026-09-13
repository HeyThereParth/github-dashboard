"""User provisioning and identity resolution."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.auth.verifier import VerifiedIdentity
from app.models.user import User
from app.repositories.user_repository import UserRepository, user_repository


class UserService:
    """Business logic for resolving a verified identity into an internal User."""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def get_or_create_user(self, db: AsyncSession, identity: VerifiedIdentity) -> User:
        """Find the user for ``identity``, provisioning one if it does not exist.

        Safe under concurrent first requests: the unique constraint on
        ``auth_provider_user_id`` protects us, and a constraint violation is
        recovered by re-reading the row that another request created.
        """
        user = await self._repository.get_by_auth_provider_user_id(db, identity.external_user_id)
        if user is not None:
            self._apply_profile_updates(user, identity)
            return user

        user = await self._repository.create(
            db,
            auth_provider_user_id=identity.external_user_id,
            email=identity.email,
            name=identity.name,
            avatar_url=identity.avatar_url,
        )
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            existing = await self._repository.get_by_auth_provider_user_id(
                db, identity.external_user_id
            )
            if existing is None:
                raise
            return existing
        return user

    @staticmethod
    def _apply_profile_updates(user: User, identity: VerifiedIdentity) -> None:
        """Update safe profile fields when the provider reports a change."""
        if identity.email is not None and identity.email != user.email:
            user.email = identity.email
        if identity.name is not None and identity.name != user.name:
            user.name = identity.name
        if identity.avatar_url is not None and identity.avatar_url != user.avatar_url:
            user.avatar_url = identity.avatar_url


user_service = UserService(user_repository)
