"""Task queue manager with Redis and in-process fallback."""

import asyncio
import json
import logging
import uuid

from redis.exceptions import RedisError

from app.core.redis import RedisClient, redis_client
from app.workers.tasks.sync_task import run_sync_job

logger = logging.getLogger(__name__)

SYNC_QUEUE_KEY = "github_intel:queue:sync_jobs"


class TaskQueue:
    """Manages dispatching tasks to Redis or graceful in-process execution."""

    def __init__(self, redis: RedisClient = redis_client) -> None:
        self._redis = redis

    async def enqueue_sync_job(
        self,
        *,
        job_id: uuid.UUID,
        workspace_id: uuid.UUID,
        repository_id: uuid.UUID,
    ) -> str:
        """Enqueue a sync job into Redis.

        If Redis is unreachable or offline, transparently falls back to an
        in-process asyncio task so the job still runs reliably.
        """
        payload = json.dumps(
            {
                "job_id": str(job_id),
                "workspace_id": str(workspace_id),
                "repository_id": str(repository_id),
            }
        )

        try:
            client = self._redis.get_client()
            await client.lpush(SYNC_QUEUE_KEY, payload)  # type: ignore[misc]
            logger.info("Enqueued job %s to Redis queue '%s'", job_id, SYNC_QUEUE_KEY)
            return "redis"
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis unavailable (%s); executing job %s via in-process background task",
                exc,
                job_id,
            )
            asyncio.create_task(
                run_sync_job(
                    job_id=job_id,
                    workspace_id=workspace_id,
                    repository_id=repository_id,
                )
            )
            return "in_process"


task_queue = TaskQueue()
