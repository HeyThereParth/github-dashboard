"""Authentication provider integrations.

Contains the boundary that verifies identities issued by the third-party
authentication provider (Supabase Auth). The rest of the application depends on
the provider-agnostic ``TokenVerifier`` abstraction, not on Supabase.
"""

from app.integrations.auth.exceptions import InvalidTokenError, TokenVerificationError
from app.integrations.auth.verifier import SupabaseTokenVerifier, TokenVerifier, VerifiedIdentity

__all__ = [
    "InvalidTokenError",
    "SupabaseTokenVerifier",
    "TokenVerificationError",
    "TokenVerifier",
    "VerifiedIdentity",
]
