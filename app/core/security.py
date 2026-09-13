"""Security boundary.

Exposes the configured token verifier. This is the only place the rest of the
application reaches the third-party identity provider; consumers depend on the
``TokenVerifier`` abstraction so they never couple to Supabase directly.
"""

from functools import lru_cache

from app.core.config import settings
from app.integrations.auth.verifier import SupabaseTokenVerifier, TokenVerifier


@lru_cache
def get_token_verifier() -> TokenVerifier:
    """Return the configured (Supabase) token verifier singleton."""
    return SupabaseTokenVerifier(
        jwks_url=settings.supabase_jwks_url,
        issuer=settings.supabase_jwt_issuer,
        audience=settings.supabase_jwt_audience,
    )
