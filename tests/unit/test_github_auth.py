"""Unit tests for GitHub App authentication and token management."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from app.integrations.github.auth import GitHubAppAuth
from app.integrations.github.exceptions import (
    GitHubAppConfigError,
    GitHubAuthError,
    GitHubRateLimitError,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def rsa_key_pair() -> tuple[str, str]:
    """Generate an ephemeral RSA private/public key pair for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def test_generate_app_jwt_success(rsa_key_pair: tuple[str, str]) -> None:
    private_pem, public_pem = rsa_key_pair
    auth = GitHubAppAuth(app_id="123456", private_key=private_pem)

    token = auth.generate_app_jwt()
    assert isinstance(token, str)

    # Decode and verify with public key
    decoded = jwt.decode(token, public_pem, algorithms=["RS256"], audience=None)
    assert decoded["iss"] == "123456"
    assert "exp" in decoded
    assert "iat" in decoded
    # Expiry should be roughly 10 minutes from now
    assert decoded["exp"] - decoded["iat"] == 11 * 60  # 10 min + 60s drift


def test_generate_app_jwt_escaped_newlines(rsa_key_pair: tuple[str, str]) -> None:
    private_pem, public_pem = rsa_key_pair
    # Simulate single-line environment variable format with escaped newlines
    escaped_pem = private_pem.replace("\n", "\\n")
    auth = GitHubAppAuth(app_id="99999", private_key=escaped_pem)

    token = auth.generate_app_jwt()
    decoded = jwt.decode(token, public_pem, algorithms=["RS256"], audience=None)
    assert decoded["iss"] == "99999"


def test_generate_app_jwt_missing_config() -> None:
    auth = GitHubAppAuth(app_id=None, private_key=None)
    with pytest.raises(GitHubAppConfigError, match="must be configured"):
        auth.generate_app_jwt()


def test_get_installation_token_success_and_caching(rsa_key_pair: tuple[str, str]) -> None:
    async def _run() -> None:
        private_pem, _ = rsa_key_pair
        mock_client = AsyncMock()

        future_expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "token": "ghs_test_token_123",
            "expires_at": future_expiry,
        }
        mock_client.post.return_value = mock_response

        auth = GitHubAppAuth(
            app_id="12345",
            private_key=private_pem,
            http_client=mock_client,
        )

        # First call: hits the API
        token1 = await auth.get_installation_token(1001)
        assert token1 == "ghs_test_token_123"
        assert mock_client.post.call_count == 1

        # Second call: served from memory cache
        token2 = await auth.get_installation_token(1001)
        assert token2 == "ghs_test_token_123"
        assert mock_client.post.call_count == 1  # No second network call!

    import asyncio

    asyncio.run(_run())


def test_get_installation_token_rate_limit(rsa_key_pair: tuple[str, str]) -> None:
    async def _run() -> None:
        private_pem, _ = rsa_key_pair
        mock_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "API rate limit exceeded for installation"
        mock_response.headers = {"x-ratelimit-reset": "1700000000"}
        mock_client.post.return_value = mock_response

        auth = GitHubAppAuth(
            app_id="12345",
            private_key=private_pem,
            http_client=mock_client,
        )

        with pytest.raises(GitHubRateLimitError) as exc_info:
            await auth.get_installation_token(1001)

        assert exc_info.value.reset_at == 1700000000

    import asyncio

    asyncio.run(_run())


def test_get_installation_token_auth_error(rsa_key_pair: tuple[str, str]) -> None:
    async def _run() -> None:
        private_pem, _ = rsa_key_pair
        mock_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"
        mock_client.post.return_value = mock_response

        auth = GitHubAppAuth(
            app_id="12345",
            private_key=private_pem,
            http_client=mock_client,
        )

        with pytest.raises(GitHubAuthError, match="Failed to obtain installation token"):
            await auth.get_installation_token(1001)

    import asyncio

    asyncio.run(_run())
