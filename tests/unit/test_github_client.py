"""Unit tests for GitHub REST API client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.integrations.github.client import (
    GitHubClient,
    GitHubPullRequestData,
    GitHubRepositoryData,
)
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


def test_list_repository_pull_requests_success() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_test_token"

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 555,
                "node_id": "PR_kwDO123",
                "number": 12,
                "title": "Fix memory leak in background worker",
                "state": "closed",
                "draft": False,
                "user": {"login": "octocat"},
                "html_url": "https://github.com/acme/backend/pull/12",
                "merged_at": "2024-03-01T15:00:00Z",
                "closed_at": "2024-03-01T15:00:00Z",
                "created_at": "2024-02-28T10:00:00Z",
                "updated_at": "2024-03-01T15:00:00Z",
            }
        ]
        mock_client.request.return_value = mock_response

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        prs = await client.list_repository_pull_requests(
            12345, owner="acme", repo="backend", state="all"
        )

        assert len(prs) == 1
        pr = prs[0]
        assert isinstance(pr, GitHubPullRequestData)
        assert pr.github_id == 555
        assert pr.number == 12
        assert pr.author_login == "octocat"
        assert pr.state == "closed"
        assert pr.draft is False
        assert pr.merged_at is not None

    asyncio.run(_run())


def test_fetch_all_pull_requests_pagination() -> None:
    async def _run() -> None:
        mock_auth = AsyncMock()
        mock_auth.get_installation_token.return_value = "ghs_test_token"

        mock_client = AsyncMock()

        # Simulate 2 pages: page 1 has 100 PRs, page 2 has 2 PRs
        page1_data = [
            {
                "id": i,
                "node_id": f"PR_{i}",
                "number": i,
                "title": f"PR {i}",
                "state": "open",
                "draft": False,
                "user": {"login": "dev"},
                "html_url": f"https://github.com/acme/backend/pull/{i}",
                "merged_at": None,
                "closed_at": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
            for i in range(1, 101)
        ]
        page2_data = [
            {
                "id": 101,
                "node_id": "PR_101",
                "number": 101,
                "title": "PR 101",
                "state": "closed",
                "draft": False,
                "user": None,
                "html_url": "https://github.com/acme/backend/pull/101",
                "merged_at": None,
                "closed_at": "2024-01-02T00:00:00Z",
                "created_at": "2024-01-02T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
            }
        ]

        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = page1_data

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = page2_data

        mock_client.request.side_effect = [resp1, resp2]

        client = GitHubClient(auth=mock_auth, http_client=mock_client)
        all_prs = await client.fetch_all_pull_requests(
            12345, owner="acme", repo="backend", state="all"
        )

        assert len(all_prs) == 101
        assert mock_client.request.call_count == 2
        assert all_prs[-1].author_login is None

    asyncio.run(_run())
