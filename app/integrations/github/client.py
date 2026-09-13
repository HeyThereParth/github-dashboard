"""GitHub REST API client."""

from dataclasses import dataclass
from datetime import datetime
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


def _parse_github_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string from GitHub API into a timezone-aware datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


@dataclass(frozen=True)
class GitHubPullRequestData:
    """Strongly-typed mirror of a GitHub pull request from API responses."""

    github_id: int
    node_id: str
    number: int
    title: str
    state: str
    draft: bool
    html_url: str
    github_created_at: datetime
    github_updated_at: datetime
    author_login: str | None = None
    merged_at: datetime | None = None
    closed_at: datetime | None = None

    @classmethod
    def from_api_payload(cls, data: dict[str, Any]) -> "GitHubPullRequestData":
        """Parse raw GitHub API dictionary into GitHubPullRequestData."""
        user = data.get("user")
        author_login = (
            str(user["login"])
            if isinstance(user, dict) and "login" in user and user["login"]
            else None
        )

        created_at_dt = _parse_github_datetime(data.get("created_at"))
        updated_at_dt = _parse_github_datetime(data.get("updated_at"))
        if created_at_dt is None or updated_at_dt is None:
            raise GitHubAPIError(
                "Pull request missing required timestamp fields ('created_at' / 'updated_at')"
            )

        return cls(
            github_id=int(data["id"]),
            node_id=str(data["node_id"]),
            number=int(data["number"]),
            title=str(data["title"]),
            state=str(data["state"]),
            draft=bool(data.get("draft", False)),
            author_login=author_login,
            html_url=str(data["html_url"]),
            merged_at=_parse_github_datetime(data.get("merged_at")),
            closed_at=_parse_github_datetime(data.get("closed_at")),
            github_created_at=created_at_dt,
            github_updated_at=updated_at_dt,
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
    ) -> Any:
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

        result: Any = response.json()
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
        if not isinstance(payload, dict):
            raise GitHubAPIError("Expected dictionary response from /installation/repositories")
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
        if not isinstance(payload, dict):
            raise GitHubAPIError(f"Expected dictionary response from /repos/{owner}/{repo}")
        return GitHubRepositoryData.from_api_payload(payload)

    async def list_repository_pull_requests(
        self,
        installation_id: int,
        *,
        owner: str,
        repo: str,
        state: str = "all",
        page: int = 1,
        per_page: int = 100,
    ) -> list[GitHubPullRequestData]:
        """Fetch a single page of pull requests for a repository.

        Endpoint: GET /repos/{owner}/{repo}/pulls
        """
        params: dict[str, Any] = {
            "state": state,
            "page": page,
            "per_page": per_page,
        }
        payload = await self._request(
            installation_id, "GET", f"/repos/{owner}/{repo}/pulls", params=params
        )
        if not isinstance(payload, list):
            raise GitHubAPIError(
                f"Unexpected response format for pull requests: expected list, got {type(payload)}"
            )
        return [GitHubPullRequestData.from_api_payload(item) for item in payload]

    async def fetch_all_pull_requests(
        self,
        installation_id: int,
        *,
        owner: str,
        repo: str,
        state: str = "all",
        max_pages: int = 50,
    ) -> list[GitHubPullRequestData]:
        """Fetch all pull requests across multiple pages.

        Safeguarded by `max_pages` to prevent infinite loops and rate-limit exhaustion.
        """
        all_prs: list[GitHubPullRequestData] = []
        page = 1
        per_page = 100

        while page <= max_pages:
            prs = await self.list_repository_pull_requests(
                installation_id,
                owner=owner,
                repo=repo,
                state=state,
                page=page,
                per_page=per_page,
            )
            all_prs.extend(prs)
            if len(prs) < per_page:
                break
            page += 1

        return all_prs


def create_github_client(
    auth: GitHubAppAuth = github_app_auth,
    http_client: httpx.AsyncClient | None = None,
) -> GitHubClient:
    """Factory function for creating GitHubClient instances."""
    return GitHubClient(auth=auth, http_client=http_client)


github_client = create_github_client()
