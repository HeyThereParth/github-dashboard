"""Exceptions raised by the auth provider verification boundary."""


class TokenVerificationError(Exception):
    """Base error for token verification failures."""


class InvalidTokenError(TokenVerificationError):
    """The provided token is malformed, invalid, or expired."""
