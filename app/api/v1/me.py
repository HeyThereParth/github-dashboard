"""Current-user routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's application-level profile."""
    return UserResponse.model_validate(current_user)
