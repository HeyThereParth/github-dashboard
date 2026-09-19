"""Unit tests for GitHub Webhook verification and route processing."""

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, patch

from app.integrations.github.webhooks import verify_webhook_signature
from app.main import app
from app.models.repository import Repository
from app.services.webhook_service import WebhookService
from fastapi.testclient import TestClient

SECRET = "super_secret_webhook_key_123"


def _sign_payload(body: bytes, secret: str = SECRET) -> str:
    """Helper to generate GitHub-compatible X-Hub-Signature-256 header."""
    digest = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ==============================================================================
# Signature Verifier Tests
# ==============================================================================


def test_verify_webhook_signature_valid() -> None:
    payload = b'{"action": "opened"}'
    signature = _sign_payload(payload, SECRET)
    assert verify_webhook_signature(payload, signature, SECRET) is True


def test_verify_webhook_signature_tampered_payload() -> None:
    payload = b'{"action": "opened"}'
    signature = _sign_payload(payload, SECRET)
    tampered_payload = b'{"action": "closed"}'
    assert verify_webhook_signature(tampered_payload, signature, SECRET) is False


def test_verify_webhook_signature_wrong_secret() -> None:
    payload = b'{"action": "opened"}'
    signature = _sign_payload(payload, "wrong_secret")
    assert verify_webhook_signature(payload, signature, SECRET) is False


def test_verify_webhook_signature_missing_or_malformed() -> None:
    payload = b'{"action": "opened"}'
    assert verify_webhook_signature(payload, None, SECRET) is False
    assert verify_webhook_signature(payload, "", SECRET) is False
    assert verify_webhook_signature(payload, "invalid_no_prefix", SECRET) is False


# ==============================================================================
# WebhookService Tests
# ==============================================================================


def test_webhook_service_ping() -> None:
    import asyncio

    async def _run() -> None:
        service = WebhookService()
        result = await service.process_github_event(
            AsyncMock(), event="ping", payload={"zen": "Approachable is better than simple."}
        )
        assert result["status"] == "pong"
        assert result["zen"] == "Approachable is better than simple."

    asyncio.run(_run())


def test_webhook_service_pull_request_processed() -> None:
    import asyncio

    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_pr_repo = AsyncMock()

        repo = Repository(
            workspace_id=uuid.uuid4(),
            github_id=999,
            node_id="R_123",
            name="github-dashboard",
            full_name="HeyThereParth/github-dashboard",
            owner_login="HeyThereParth",
            private=False,
            html_url="https://github.com/HeyThereParth/github-dashboard",
            default_branch="main",
            is_tracked=True,
        )
        repo.id = uuid.uuid4()
        mock_repo_repo.list_by_github_id.return_value = [repo]
        mock_pr_repo.upsert_batch.return_value = 1

        service = WebhookService(
            repository_repo=mock_repo_repo,
            pull_request_repo=mock_pr_repo,
            analytics=AsyncMock(),
        )

        payload = {
            "action": "opened",
            "repository": {"id": 999, "name": "github-dashboard"},
            "pull_request": {
                "id": 888,
                "node_id": "PR_888",
                "number": 5,
                "title": "Add webhook support",
                "state": "open",
                "draft": False,
                "user": {"login": "octocat"},
                "html_url": "https://github.com/HeyThereParth/github-dashboard/pull/5",
                "merged_at": None,
                "closed_at": None,
                "created_at": "2024-03-01T12:00:00Z",
                "updated_at": "2024-03-01T12:00:00Z",
            },
        }

        result = await service.process_github_event(mock_db, event="pull_request", payload=payload)
        assert result["status"] == "processed"
        assert result["action"] == "opened"
        assert result["pr_number"] == 5
        mock_pr_repo.upsert_batch.assert_called_once()

    asyncio.run(_run())


def test_webhook_service_invalidates_analytics_cache() -> None:
    import asyncio

    async def _run() -> None:
        mock_db = AsyncMock()
        mock_repo_repo = AsyncMock()
        mock_pr_repo = AsyncMock()
        mock_analytics = AsyncMock()

        repo = Repository(
            workspace_id=uuid.uuid4(),
            github_id=999,
            node_id="R_123",
            name="github-dashboard",
            full_name="HeyThereParth/github-dashboard",
            owner_login="HeyThereParth",
            private=False,
            html_url="https://github.com/HeyThereParth/github-dashboard",
            default_branch="main",
            is_tracked=True,
        )
        repo.id = uuid.uuid4()
        mock_repo_repo.list_by_github_id.return_value = [repo]
        mock_pr_repo.upsert_batch.return_value = 1

        service = WebhookService(
            repository_repo=mock_repo_repo,
            pull_request_repo=mock_pr_repo,
            analytics=mock_analytics,
        )

        payload = {
            "action": "closed",
            "repository": {"id": 999, "name": "github-dashboard"},
            "pull_request": {
                "id": 888,
                "node_id": "PR_888",
                "number": 5,
                "title": "Add webhook support",
                "state": "closed",
                "draft": False,
                "user": {"login": "octocat"},
                "html_url": "https://github.com/HeyThereParth/github-dashboard/pull/5",
                "merged_at": "2024-03-01T15:00:00Z",
                "closed_at": "2024-03-01T15:00:00Z",
                "created_at": "2024-03-01T12:00:00Z",
                "updated_at": "2024-03-01T15:00:00Z",
            },
        }

        await service.process_github_event(mock_db, event="pull_request", payload=payload)
        mock_analytics.invalidate_repository_cache.assert_called_once_with(repo.id)

    asyncio.run(_run())


# ==============================================================================
# Webhook Route Integration Tests
# ==============================================================================


def test_webhook_route_ping() -> None:
    client = TestClient(app)
    body = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    sig = _sign_payload(body, SECRET)

    with patch("app.api.v1.webhooks.settings.github_webhook_secret", SECRET):
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": sig,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pong"


def test_webhook_route_invalid_signature() -> None:
    client = TestClient(app)
    body = json.dumps({"zen": "test"}).encode("utf-8")

    with patch("app.api.v1.webhooks.settings.github_webhook_secret", SECRET):
        response = client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": "sha256=invalid_hash",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401
        assert "Invalid or missing webhook signature" in response.json()["detail"]
