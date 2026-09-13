"""Shared FastAPI dependencies for authentication and workspace authorization."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_token_verifier
from app.integrations.auth.exceptions import InvalidTokenError
from app.integrations.auth.verifier import TokenVerifier
from app.models.user import User
from app.models.workspace import Workspace
from app.services.user_service import user_service
from app.services.workspace_service import (
    WorkspaceForbiddenError,
    WorkspaceNotFoundError,
    workspace_service,
)


def _extract_bearer_token(authorization: str | None) -> str:
    """Return the bearer token from the Authorization header, or raise 401."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> User:
    """Resolve the verified provider identity into our internal User."""
    token = _extract_bearer_token(authorization)
    try:
        identity = await verifier.verify(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return await user_service.get_or_create_user(db, identity)


async def get_accessible_workspace(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Return the workspace only if the current user is a member.

    Reusable across resources (repositories, issues, PRs, ...) by depending on
    the same workspace access rule.
    """
    try:
        return await workspace_service.get_workspace_for_member(
            db, workspace_id=workspace_id, user_id=current_user.id
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        ) from exc
    except WorkspaceForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace",
        ) from exc
