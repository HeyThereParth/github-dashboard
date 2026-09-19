"""GitHub Webhook event processing service."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.github.client import GitHubPullRequestData
from app.repositories.pull_request_repository import (
    PullRequestRepository,
    pull_request_repository,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository,
)
from app.services.analytics_service import AnalyticsService, analytics_service

logger = logging.getLogger(__name__)


class WebhookService:
    """Processes incoming GitHub webhook events and updates local mirrors."""

    def __init__(
        self,
        repository_repo: RepositoryRepository = repository_repository,
        pull_request_repo: PullRequestRepository = pull_request_repository,
        analytics: AnalyticsService = analytics_service,
    ) -> None:
        self._repository_repo = repository_repo
        self._pull_request_repo = pull_request_repo
        self._analytics = analytics

    async def process_github_event(
        self,
        db: AsyncSession,
        *,
        event: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Route and process an authenticated GitHub webhook event."""
        if event == "ping":
            zen = payload.get("zen", "Keep it logically awesome.")
            logger.info("Received GitHub ping event: %s", zen)
            return {"status": "pong", "zen": zen}

        if event == "pull_request":
            return await self._handle_pull_request_event(db, payload)

        logger.debug("Unhandled GitHub webhook event: %s", event)
        return {"status": "ignored", "event": event}

    async def _handle_pull_request_event(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle pull_request events (opened, closed, synchronize, edited, reopened)."""
        action = payload.get("action")
        pr_raw = payload.get("pull_request")
        repo_raw = payload.get("repository")

        if not pr_raw or not repo_raw or "id" not in repo_raw:
            return {"status": "ignored", "reason": "missing_pull_request_or_repository"}

        github_repo_id = int(repo_raw["id"])
        tracked_repos = await self._repository_repo.list_by_github_id(db, github_id=github_repo_id)

        if not tracked_repos:
            logger.info(
                "Ignoring pull_request event for untracked repository github_id=%d",
                github_repo_id,
            )
            return {"status": "ignored", "reason": "repository_not_tracked"}

        pr_data = GitHubPullRequestData.from_api_payload(pr_raw)

        for repo in tracked_repos:
            await self._pull_request_repo.upsert_batch(
                db,
                repository_id=repo.id,
                pull_requests=[pr_data],
            )
            # Fresh PR data invalidates cached analytics (soft-fails if Redis is offline)
            await self._analytics.invalidate_repository_cache(repo.id)

        logger.info(
            "Processed pull_request event '%s' for PR #%d across %d workspace repositories",
            action,
            pr_data.number,
            len(tracked_repos),
        )

        return {
            "status": "processed",
            "action": action,
            "pr_number": pr_data.number,
            "matched_repositories": len(tracked_repos),
        }


webhook_service = WebhookService()
