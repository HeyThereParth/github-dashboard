"""GitHub App authentication and installation token management."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import Settings, settings
from app.integrations.github.exceptions import (
    GitHubAppConfigError,
    GitHubAuthError,
    GitHubRateLimitError,
)


@dataclass(frozen=True)
class InstallationToken:
    """Represents a temporary GitHub App installation access token."""

    token: str
    expires_at: datetime


def _load_private_key(key_or_path: str) -> str:
    """Load and normalize an RSA private key from PEM string or file path."""
    stripped = key_or_path.strip()
    if stripped.startswith("-----BEGIN"):
        if "\\n" in stripped and "\n" not in stripped:
            return stripped.replace("\\n", "\n")
        return stripped

    path = Path(stripped)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()

    # Fallback to string with replaced newlines
    return stripped.replace("\\n", "\n")


class GitHubAppAuth:
    """Manages GitHub App JWT generation and short-lived installation access tokens."""

    def __init__(
        self,
        *,
        app_id: str | None = None,
        private_key: str | None = None,
        api_url: str = "https://api.github.com",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._api_url = api_url.rstrip("/")
        self._http_client = http_client
        self._token_cache: dict[int, InstallationToken] = {}

    def generate_app_jwt(self) -> str:
        """Create a signed JWT representing the GitHub App.

        The JWT is valid for up to 10 minutes, with a 60-second drift tolerance
        as recommended by GitHub's documentation.
        """
        if not self._app_id or not self._private_key:
            raise GitHubAppConfigError(
                "GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be configured"
            )

        now = int(time.time())
        payload: dict[str, Any] = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": str(self._app_id),
        }

        try:
            pem_key = _load_private_key(self._private_key)
            token = jwt.encode(payload, pem_key, algorithm="RS256")
            return str(token)
        except Exception as exc:
            raise GitHubAuthError(f"Failed to sign GitHub App JWT: {exc}") from exc

    async def get_installation_token(self, installation_id: int) -> str:
        """Return a valid installation access token, using the cache if not near expiry."""
        now = datetime.now(UTC)
        cached = self._token_cache.get(installation_id)
        if cached and cached.expires_at > now + timedelta(minutes=5):
            return cached.token

        app_jwt = self.generate_app_jwt()
        url = f"{self._api_url}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {app_jwt}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        client = self._http_client
        should_close = False
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            response = await client.post(url, headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubAuthError(f"Network error requesting installation token: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_header = response.headers.get("x-ratelimit-reset")
            reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
            raise GitHubRateLimitError("GitHub API rate limit exceeded", reset_at=reset_at)

        if response.status_code != 201:
            raise GitHubAuthError(
                f"Failed to obtain installation token (status {response.status_code}): "
                f"{response.text}"
            )

        data = response.json()
        token = str(data["token"])
        expires_at_raw = str(data["expires_at"])
        expires_at = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))

        self._token_cache[installation_id] = InstallationToken(token=token, expires_at=expires_at)
        return token


def create_github_app_auth(current_settings: Settings = settings) -> GitHubAppAuth:
    """Factory creating GitHubAppAuth from application settings."""
    return GitHubAppAuth(
        app_id=current_settings.github_app_id,
        private_key=current_settings.github_app_private_key,
        api_url=current_settings.github_api_url,
    )


github_app_auth = create_github_app_auth()
