"""GitHub REST API client."""

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.github.auth import GitHubAppAuth, github_app_auth
from app.integrations.github.exceptions import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)


@dataclass(frozen=True)
class GitHubRepositoryData:
    """Strongly-typed mirror of a GitHub repository from API responses."""

    github_id: int
    node_id: str
    name: str
    full_name: str
    private: bool
    html_url: str
    default_branch: str
    description: str | None = None

    @classmethod
    def from_api_payload(cls, data: dict[str, Any]) -> "GitHubRepositoryData":
        """Parse raw GitHub API dictionary into GitHubRepositoryData."""
        return cls(
            github_id=int(data["id"]),
            node_id=str(data["node_id"]),
            name=str(data["name"]),
            full_name=str(data["full_name"]),
            private=bool(data["private"]),
            html_url=str(data["html_url"]),
            default_branch=str(data.get("default_branch") or "main"),
            description=data.get("description"),
        )


class GitHubClient:
    """Asynchronous client for interacting with the GitHub REST API on behalf of an installation."""

    def __init__(
        self,
        auth: GitHubAppAuth = github_app_auth,
        *,
        api_url: str = settings.github_api_url,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._auth = auth
        self._api_url = api_url.rstrip("/")
        self._http_client = http_client

    async def _request(
        self,
        installation_id: int,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated request using the installation's access token."""
        token = await self._auth.get_installation_token(installation_id)
        url = f"{self._api_url}/{endpoint.lstrip('/')}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        client = self._http_client
        should_close = False
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            response = await client.request(method, url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise GitHubAPIError(
                f"Network error during GitHub API request: {exc}", status_code=0
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 404:
            raise GitHubNotFoundError(f"GitHub resource not found: {endpoint}")

        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_header = response.headers.get("x-ratelimit-reset")
            reset_at = int(reset_header) if reset_header and reset_header.isdigit() else None
            raise GitHubRateLimitError("GitHub API rate limit exceeded", reset_at=reset_at)

        if response.status_code == 401:
            raise GitHubAuthError(f"GitHub authentication failed: {response.text}")

        if not (200 <= response.status_code < 300):
            raise GitHubAPIError(
                f"GitHub API error (status {response.status_code}): {response.text}",
                status_code=response.status_code,
            )

        result: dict[str, Any] = response.json()
        return result

    async def list_installation_repositories(
        self,
        installation_id: int,
        *,
        page: int = 1,
        per_page: int = 100,
    ) -> list[GitHubRepositoryData]:
        """Fetch all repositories accessible to the GitHub App installation.

        Endpoint: GET /installation/repositories
        """
        params = {"page": page, "per_page": per_page}
        payload = await self._request(
            installation_id, "GET", "/installation/repositories", params=params
        )
        raw_repos: list[dict[str, Any]] = payload.get("repositories", [])
        return [GitHubRepositoryData.from_api_payload(r) for r in raw_repos]

    async def get_repository(
        self,
        installation_id: int,
        *,
        owner: str,
        repo: str,
    ) -> GitHubRepositoryData:
        """Fetch details for a single repository.

        Endpoint: GET /repos/{owner}/{repo}
        """
        payload = await self._request(installation_id, "GET", f"/repos/{owner}/{repo}")
        return GitHubRepositoryData.from_api_payload(payload)


def create_github_client(
    auth: GitHubAppAuth = github_app_auth,
    http_client: httpx.AsyncClient | None = None,
) -> GitHubClient:
    """Factory function for creating GitHubClient instances."""
    return GitHubClient(auth=auth, http_client=http_client)


github_client = create_github_client()
