"""User API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Application-level representation of the current user.

    Deliberately excludes the provider identity (``auth_provider_user_id``) and
    any provider tokens.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    name: str | None
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime
