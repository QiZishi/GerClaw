"""Replica-safe cancellation signalling for active chat turns."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import suppress

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_CHANNEL = "gerclaw:chat:cancellations:v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{3,128}$")
_CANCEL_TTL_SECONDS = 120
TaskKey = tuple[str, str, str]


class ChatCancellationUnavailable(RuntimeError):
    """Raised when a durable cancellation request cannot be coordinated."""


class ChatCancellationRegistry:
    """Fan out cancellation through Redis while keeping one listener per replica."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._tasks: dict[TaskKey, asyncio.Task[None]] = {}
        self._requested: set[TaskKey] = set()
        self._lock = asyncio.Lock()
        self._listener: asyncio.Task[None] | None = None
        self._pubsub: object | None = None

    async def start(self) -> None:
        """Subscribe before the application accepts chat requests."""

        if self._listener is not None:
            return
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(_CHANNEL)
        self._pubsub = pubsub
        self._listener = asyncio.create_task(
            self._listen(pubsub),
            name="gerclaw-chat-cancellation-listener",
        )

    async def aclose(self) -> None:
        """Release the dedicated Pub/Sub connection without cancelling chat turns."""

        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener
        pubsub = self._pubsub
        self._pubsub = None
        if pubsub is not None:
            with suppress(Exception):
                await pubsub.unsubscribe(_CHANNEL)  # type: ignore[attr-defined]
            with suppress(Exception):
                await pubsub.aclose()  # type: ignore[attr-defined]

    async def register(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """Register a local owner and honor any cancellation that won the startup race."""

        key = (tenant_id, actor_id, trace_id)
        async with self._lock:
            self._tasks[key] = task
        try:
            already_requested = bool(await self._redis.exists(self._request_key(*key)))
        except Exception as error:
            async with self._lock:
                if self._tasks.get(key) is task:
                    self._tasks.pop(key, None)
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        if already_requested and not task.done() and task.cancelling() == 0:
            async with self._lock:
                if self._tasks.get(key) is task:
                    self._requested.add(key)
            task.cancel("explicit chat cancellation requested")

    async def unregister(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
        task: asyncio.Task[None],
    ) -> None:
        """Remove only the task that still owns the local registry entry."""

        key = (tenant_id, actor_id, trace_id)
        async with self._lock:
            if self._tasks.get(key) is task:
                self._tasks.pop(key, None)
                self._requested.discard(key)

    async def request_cancel(self, *, tenant_id: str, actor_id: str, trace_id: str) -> None:
        """Persist and publish an identity-scoped cancellation request."""

        key = (tenant_id, actor_id, trace_id)
        payload = json.dumps(
            {"tenant_id": tenant_id, "actor_id": actor_id, "trace_id": trace_id},
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            async with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.set(self._request_key(*key), "1", ex=_CANCEL_TTL_SECONDS)
                pipeline.publish(_CHANNEL, payload)
                await pipeline.execute()
        except Exception as error:
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        await self._cancel_local(key)

    async def is_cancel_requested(self, *, tenant_id: str, actor_id: str, trace_id: str) -> bool:
        """Return the durable intent used as a final pre-commit cancellation fence."""

        key = (tenant_id, actor_id, trace_id)
        async with self._lock:
            if key in self._requested:
                return True
        try:
            requested = bool(
                await self._redis.exists(self._request_key(tenant_id, actor_id, trace_id))
            )
        except Exception as error:
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        if requested:
            async with self._lock:
                if key in self._tasks:
                    self._requested.add(key)
        return requested

    async def _listen(self, pubsub: object) -> None:
        try:
            while True:
                message = await pubsub.get_message(timeout=1.0)  # type: ignore[attr-defined]
                if not isinstance(message, dict):
                    await asyncio.sleep(0)
                    continue
                key = self._parse_message(message.get("data"))
                if key is not None:
                    await self._cancel_local(key)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Redis readiness and the cancel endpoint fail closed separately. Do not
            # include payloads or identities in process logs.
            logger.exception("chat_cancellation_listener_failed")

    async def _cancel_local(self, key: TaskKey) -> None:
        async with self._lock:
            task = self._tasks.get(key)
            if task is not None and not task.done():
                self._requested.add(key)
        if task is not None and not task.done() and task.cancelling() == 0:
            task.cancel("explicit chat cancellation requested")

    @staticmethod
    def _parse_message(raw: object) -> TaskKey | None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if not isinstance(raw, str) or len(raw) > 512:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or set(payload) != {"tenant_id", "actor_id", "trace_id"}:
            return None
        values = (payload["tenant_id"], payload["actor_id"], payload["trace_id"])
        if any(not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None for value in values):
            return None
        return values

    @staticmethod
    def _request_key(tenant_id: str, actor_id: str, trace_id: str) -> str:
        return f"gerclaw:chat:cancel:v1:{tenant_id}:{actor_id}:{trace_id}"
