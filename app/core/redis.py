"""Resilient Redis cache client."""

import logging

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Resilient async Redis client with soft-fail degradation.

    If Redis is offline, unreachable, or times out, calls log a warning
    and gracefully return None/False so the application continues working.
    """

    def __init__(self, redis_url: str = settings.redis_url) -> None:
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None

    def get_client(self) -> aioredis.Redis:
        """Return the initialized async Redis client instance."""
        if self._client is None:
            self._client = aioredis.from_url(  # type: ignore[no-untyped-call]
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
        return self._client

    async def get(self, key: str) -> str | None:
        """Fetch value from cache, returning None on cache miss or connection failure."""
        try:
            client = self.get_client()
            val = await client.get(key)
            return str(val) if val is not None else None
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis GET failed for key '%s': %s (degrading to direct DB query)",
                key,
                exc,
            )
            return None

    async def set(self, key: str, value: str, ttl_seconds: int = 900) -> bool:
        """Store value with a TTL (default 15 minutes), returning False on failure."""
        try:
            client = self.get_client()
            await client.set(key, value, ex=ttl_seconds)
            return True
        except (RedisError, OSError) as exc:
            logger.warning("Redis SET failed for key '%s': %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a single key from cache."""
        try:
            client = self.get_client()
            await client.delete(key)
            return True
        except (RedisError, OSError) as exc:
            logger.warning("Redis DELETE failed for key '%s': %s", key, exc)
            return False

    async def delete_prefix(self, prefix: str) -> int:
        """Invalidate all keys matching a prefix (e.g. 'analytics:repo:{id}:*')."""
        try:
            client = self.get_client()
            cursor: int = 0
            deleted_count = 0
            while True:
                scan_res = await client.scan(cursor=cursor, match=f"{prefix}*", count=100)
                cursor = int(scan_res[0])
                keys = scan_res[1]
                if keys:
                    deleted_count += await client.delete(*keys)
                if cursor == 0:
                    break
            return deleted_count
        except (RedisError, OSError) as exc:
            logger.warning("Redis delete_prefix failed for '%s': %s", prefix, exc)
            return 0

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


redis_client = RedisClient()
