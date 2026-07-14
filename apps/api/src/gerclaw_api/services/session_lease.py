"""Redis-backed single in-flight turn lease with owner fencing."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class SessionBusyError(RuntimeError):
    """Raised when another API replica owns the same conversation turn."""


class SessionLeaseUnavailableError(RuntimeError):
    """Raised when Redis cannot guarantee session serialization."""


class SessionLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the lease it must fence writes with."""


@dataclass(frozen=True, slots=True)
class SessionLeaseGuard:
    """Current Redis owner plus the monotonic PostgreSQL fencing token."""

    redis: Redis
    key: str
    owner_value: str
    fencing_token: int
    ttl_seconds: int

    async def assert_owned(self) -> None:
        """Atomically validate and extend ownership before terminal persistence."""

        try:
            renewed = await cast(
                Awaitable[Any],
                self.redis.eval(
                    _RENEW_SCRIPT,
                    1,
                    self.key,
                    self.owner_value,
                    str(self.ttl_seconds * 1_000),
                ),
            )
        except RedisError as error:
            raise SessionLeaseUnavailableError(
                "conversation serialization service is unavailable"
            ) from error
        if int(renewed) != 1:
            raise SessionLeaseLostError("conversation lease ownership was superseded")


class SessionLease:
    """Acquire, renew, and owner-conditionally release one session lease."""

    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @asynccontextmanager
    async def acquire(
        self,
        *,
        tenant_id: str,
        session_id: uuid.UUID,
        fencing_token: int,
    ) -> AsyncIterator[SessionLeaseGuard]:
        if fencing_token <= 0:
            raise ValueError("fencing_token must be positive")
        key = f"gerclaw:chat:lease:{tenant_id}:{session_id}"
        owner_value = f"{fencing_token}:{secrets.token_urlsafe(32)}"
        try:
            acquired = await self._redis.set(key, owner_value, nx=True, ex=self._ttl_seconds)
        except RedisError as error:
            raise SessionLeaseUnavailableError(
                "conversation serialization service is unavailable"
            ) from error
        if not acquired:
            raise SessionBusyError("another turn is already running for this session")

        owner_task = asyncio.current_task()
        guard = SessionLeaseGuard(
            redis=self._redis,
            key=key,
            owner_value=owner_value,
            fencing_token=fencing_token,
            ttl_seconds=self._ttl_seconds,
        )
        renewal = asyncio.create_task(
            self._renew(key=key, owner_value=owner_value, owner_task=owner_task),
            name=f"chat-lease-{session_id}",
        )
        try:
            yield guard
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            with suppress(RedisError):
                release = cast(
                    Awaitable[Any], self._redis.eval(_RELEASE_SCRIPT, 1, key, owner_value)
                )
                await asyncio.shield(release)
                # The finite TTL is the final cleanup guarantee; never delete without
                # comparing the owner token because a successor may already hold it.

    async def _renew(
        self,
        *,
        key: str,
        owner_value: str,
        owner_task: asyncio.Task[object] | None,
    ) -> None:
        interval = min(30.0, self._ttl_seconds / 3)
        ttl_ms = self._ttl_seconds * 1_000
        while True:
            await asyncio.sleep(interval)
            try:
                renewed = await cast(
                    Awaitable[Any],
                    self._redis.eval(_RENEW_SCRIPT, 1, key, owner_value, str(ttl_ms)),
                )
            except RedisError:
                renewed = 0
            if int(renewed) != 1:
                if owner_task is not None and not owner_task.done():
                    owner_task.cancel()
                return
