"""Standalone worker process entrypoint.

Consumes background sync jobs from Redis queue:
    python -m app.workers.worker
"""

import asyncio
import json
import logging
import signal
import uuid

from redis.exceptions import RedisError

from app.core.logging import configure_logging
from app.core.redis import redis_client
from app.workers.queue import SYNC_QUEUE_KEY
from app.workers.tasks.sync_task import run_sync_job

logger = logging.getLogger("app.workers.worker")


async def run_worker() -> None:
    """Continuously consume and process background jobs from Redis."""
    configure_logging()
    logger.info("Worker process started. Listening on Redis queue: '%s'", SYNC_QUEUE_KEY)

    client = redis_client.get_client()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        logger.info("Shutdown signal received. Stopping worker loop...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Signals not fully implemented on Windows event loop
            pass

    while not stop_event.is_set():
        try:
            # Pop job with 2-second timeout so the loop can check stop_event
            result = await client.brpop([SYNC_QUEUE_KEY], timeout=2)  # type: ignore[misc]
            if result is None:
                continue

            _, raw_payload = result
            data = json.loads(raw_payload)

            job_id = uuid.UUID(data["job_id"])
            workspace_id = uuid.UUID(data["workspace_id"])
            repository_id = uuid.UUID(data["repository_id"])

            logger.info("Worker popped job %s; starting execution", job_id)
            await run_sync_job(
                job_id=job_id,
                workspace_id=workspace_id,
                repository_id=repository_id,
            )

        except (RedisError, OSError) as exc:
            logger.warning("Redis error in worker loop: %s; sleeping 5s...", exc)
            await asyncio.sleep(5)
        except Exception as exc:
            logger.exception("Unexpected error processing worker job: %s", exc)
            await asyncio.sleep(1)

    logger.info("Worker process exited cleanly.")


if __name__ == "__main__":
    asyncio.run(run_worker())
