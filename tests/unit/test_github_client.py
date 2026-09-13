"""Unit tests for GitHub REST API client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.integrations.github.client import GitHubClient, GitHubRepositoryData
from app.integrations.github.exceptions import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)


def test_list_installation_repositories_success() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_test_token_456"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 2,
            "repositories": [
                {
                    "id": 101,
                    "node_id": "R_kgDOA1",
                    "name": "dashboard-ui",
                    "full_name": "acme/dashboard-ui",
                    "private": True,
                    "html_url": "https://github.com/acme/dashboard-ui",
                    "default_branch": "main",
                    "description": "Frontend for dashboard",
                },
                {
                    "id": 102,
                    "node_id": "R_kgDOB2",
                    "name": "backend-api",
                    "full_name": "acme/backend-api",
                    "private": False,
                    "html_url": "https://github.com/acme/backend-api",
                    "default_branch": "develop",
                    "description": None,
                },
            ],
        }
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        repos = await client.list_installation_repositories(12345)

        assert len(repos) == 2
        assert repos[0] == GitHubRepositoryData(
            github_id=101,
            node_id="R_kgDOA1",
            name="dashboard-ui",
            full_name="acme/dashboard-ui",
            private=True,
            html_url="https://github.com/acme/dashboard-ui",
            default_branch="main",
            description="Frontend for dashboard",
        )
        assert repos[1].name == "backend-api"
        assert repos[1].default_branch == "develop"

        # Verify auth token and headers were passed
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer ghs_test_token_456"
        assert call_kwargs["params"] == {"page": 1, "per_page": 100}

    asyncio.run(_run())


def test_get_repository_success() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 999,
            "node_id": "R_test999",
            "name": "core-engine",
            "full_name": "acme/core-engine",
            "private": True,
            "html_url": "https://github.com/acme/core-engine",
            "default_branch": "main",
            "description": "Core intelligence engine",
        }
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        repo = await client.get_repository(12345, owner="acme", repo="core-engine")

        assert repo.name == "core-engine"
        assert repo.node_id == "R_test999"
        assert repo.github_id == 999

    asyncio.run(_run())


def test_request_not_found() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        with pytest.raises(GitHubNotFoundError):
            await client.get_repository(12345, owner="acme", repo="missing")

    asyncio.run(_run())


def test_request_rate_limited() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "API rate limit exceeded"
        mock_response.headers = {"x-ratelimit-reset": "1800000000"}
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        with pytest.raises(GitHubRateLimitError) as exc_info:
            await client.list_installation_repositories(12345)

        assert exc_info.value.reset_at == 1800000000

    asyncio.run(_run())


def test_request_auth_failure() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Bad credentials"
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        with pytest.raises(GitHubAuthError):
            await client.list_installation_repositories(12345)

    asyncio.run(_run())


def test_request_server_error() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        with pytest.raises(GitHubAPIError) as exc_info:
            await client.list_installation_repositories(12345)

        assert exc_info.value.status_code == 500

    asyncio.run(_run())
