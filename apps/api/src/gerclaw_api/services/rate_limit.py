"""Atomic Redis-backed per-principal request limiting."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

_FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {current, ttl}
"""


class RateLimitExceeded(RuntimeError):
    """Raised when a principal has exhausted its fixed request window."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("request rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailable(RuntimeError):
    """Raised when Redis cannot safely enforce the configured limit."""


class RateLimiter:
    """Fail-closed atomic limiter shared by all protected API replicas."""

    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window_ms = window_seconds * 1_000

    async def check(self, *, tenant_id: str, actor_id: str) -> None:
        """Consume one request or raise with the remaining retry delay."""

        key = f"gerclaw:rate:{tenant_id}:{actor_id}"
        try:
            result = await cast(
                Awaitable[Any],
                self._redis.eval(_FIXED_WINDOW_SCRIPT, 1, key, str(self._window_ms)),
            )
        except RedisError as error:
            raise RateLimitUnavailable("Redis rate limiter is unavailable") from error
        if not isinstance(result, list) or len(result) != 2:  # pragma: no cover - Redis invariant
            raise RateLimitUnavailable("Redis returned an invalid rate-limit result")
        current = int(result[0])
        ttl_ms = max(0, int(result[1]))
        if current > self._limit:
            raise RateLimitExceeded(max(1, (ttl_ms + 999) // 1_000))
