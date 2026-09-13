"""Token verification boundary for the third-party identity provider."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from app.integrations.auth.exceptions import InvalidTokenError, TokenVerificationError


@dataclass(frozen=True)
class VerifiedIdentity:
    """Normalized, provider-agnostic identity extracted from a verified token."""

    external_user_id: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None


class TokenVerifier(ABC):
    """Verifies an opaque provider token and returns a normalized identity."""

    @abstractmethod
    async def verify(self, token: str) -> VerifiedIdentity:
        """Verify ``token`` and return the identity it represents."""


class SupabaseTokenVerifier(TokenVerifier):
    """Verifies Supabase Auth JWTs using the project's JWKS (asymmetric keys)."""

    def __init__(
        self,
        *,
        jwks_url: str | None,
        issuer: str | None,
        audience: str,
        algorithms: list[str] | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms or ["RS256", "ES256"]
        self._jwks_client: PyJWKClient | None = (
            PyJWKClient(jwks_url) if jwks_url is not None else None
        )

    async def verify(self, token: str) -> VerifiedIdentity:
        if self._jwks_url is None or self._issuer is None:
            raise TokenVerificationError("Supabase token verification is not configured")
        return await asyncio.to_thread(self._verify_sync, token)

    def _verify_sync(self, token: str) -> VerifiedIdentity:
        assert self._jwks_client is not None  # guarded by verify()

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "exp", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Token is invalid or expired") from exc

        external_user_id = payload.get("sub")
        if not external_user_id:
            raise InvalidTokenError("Token is missing the 'sub' claim")

        user_metadata: dict[str, Any] = payload.get("user_metadata") or {}
        name = user_metadata.get("full_name") or user_metadata.get("name")
        avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture")

        return VerifiedIdentity(
            external_user_id=str(external_user_id),
            email=payload.get("email"),
            name=name,
            avatar_url=avatar_url,
        )
