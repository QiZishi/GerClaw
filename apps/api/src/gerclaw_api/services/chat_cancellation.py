"""Replica-safe cancellation signalling for active chat turns."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import suppress
from enum import StrEnum

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_CHANNEL = "gerclaw:chat:cancellations:v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{3,128}$")
_CANCEL_TTL_SECONDS = 120
_REDELIVERY_DELAYS_SECONDS = (0.0, 0.25, 0.75, 1.5, 3.0, 5.0, 8.0, 13.0)
TaskKey = tuple[str, str, str]


class ChatControlIntent(StrEnum):
    """Durable user control intents with distinct lifecycle semantics."""

    CANCEL = "cancel"
    STEER = "steer"


class ChatCancellationUnavailable(RuntimeError):
    """Raised when a durable cancellation request cannot be coordinated."""


class ChatCancellationRegistry:
    """Fan out cancellation through Redis while keeping one listener per replica."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._tasks: dict[TaskKey, asyncio.Task[None]] = {}
        self._requested: dict[TaskKey, ChatControlIntent] = {}
        self._acknowledged: dict[TaskKey, ChatControlIntent] = {}
        self._redelivery: dict[TaskKey, asyncio.Task[None]] = {}
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

        redelivery = tuple(self._redelivery.values())
        self._redelivery.clear()
        for task in redelivery:
            task.cancel()
        if redelivery:
            await asyncio.gather(*redelivery, return_exceptions=True)
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
            stale_redelivery = self._redelivery.pop(key, None)
            self._tasks[key] = task
            self._acknowledged.pop(key, None)
        if stale_redelivery is not None:
            stale_redelivery.cancel()
        try:
            intent = await self._read_intent(key)
        except Exception as error:
            async with self._lock:
                if self._tasks.get(key) is task:
                    self._tasks.pop(key, None)
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        if intent is not None:
            await self._interrupt_local(key, intent)

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
        redelivery: asyncio.Task[None] | None = None
        async with self._lock:
            if self._tasks.get(key) is task:
                self._tasks.pop(key, None)
                self._requested.pop(key, None)
                self._acknowledged.pop(key, None)
                redelivery = self._redelivery.pop(key, None)
        if redelivery is not None:
            redelivery.cancel()

    def acknowledge_control(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
    ) -> None:
        """Stop redelivery before the owner starts durable terminal cleanup."""

        key = (tenant_id, actor_id, trace_id)
        intent = self._requested.get(key)
        if intent is None:
            return
        self._acknowledged[key] = intent
        redelivery = self._redelivery.pop(key, None)
        if redelivery is not None and redelivery is not asyncio.current_task():
            redelivery.cancel()

    async def request_cancel(self, *, tenant_id: str, actor_id: str, trace_id: str) -> None:
        """Persist and publish an identity-scoped cancellation request."""

        key = (tenant_id, actor_id, trace_id)
        await self._request_control(key, ChatControlIntent.CANCEL)

    async def request_steer(self, *, tenant_id: str, actor_id: str, trace_id: str) -> None:
        """Persist and publish an immediate-steer interruption."""

        await self._request_control(
            (tenant_id, actor_id, trace_id),
            ChatControlIntent.STEER,
        )

    async def is_cancel_requested(self, *, tenant_id: str, actor_id: str, trace_id: str) -> bool:
        """Return the durable intent used as a final pre-commit cancellation fence."""

        return (
            await self.control_intent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
            )
            is ChatControlIntent.CANCEL
        )

    async def is_steer_requested(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
    ) -> bool:
        """Return true only for an immediate-steer interruption."""

        return (
            await self.control_intent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
            )
            is ChatControlIntent.STEER
        )

    async def is_interruption_requested(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
    ) -> bool:
        """Fence final answer promotion for either user control intent."""

        return (
            await self.control_intent(
                tenant_id=tenant_id,
                actor_id=actor_id,
                trace_id=trace_id,
            )
            is not None
        )

    async def control_intent(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        trace_id: str,
    ) -> ChatControlIntent | None:
        """Read the durable intent, with explicit cancel taking precedence."""

        key = (tenant_id, actor_id, trace_id)
        async with self._lock:
            local = self._requested.get(key)
        if local is ChatControlIntent.CANCEL:
            return local
        try:
            intent = await self._read_intent(key)
        except ChatCancellationUnavailable:
            # A control request already delivered to this worker remains an
            # authoritative final fence even if Redis fails during cleanup.
            if local is not None:
                return local
            raise
        if intent is not None:
            async with self._lock:
                effective = self._merge_intent(
                    self._requested.get(key) if key in self._tasks else local,
                    intent,
                )
                if key in self._tasks:
                    self._requested[key] = effective
                return effective
        return local

    async def _request_control(
        self,
        key: TaskKey,
        intent: ChatControlIntent,
    ) -> None:
        payload = json.dumps(
            {
                "tenant_id": key[0],
                "actor_id": key[1],
                "trace_id": key[2],
                "intent": intent.value,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            async with self._redis.pipeline(transaction=True) as pipeline:
                pipeline.set(
                    self._request_key(*key, intent=intent),
                    "1",
                    ex=_CANCEL_TTL_SECONDS,
                )
                pipeline.publish(_CHANNEL, payload)
                await pipeline.execute()
        except Exception as error:
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        await self._interrupt_local(key, intent)

    async def _read_intent(self, key: TaskKey) -> ChatControlIntent | None:
        try:
            cancel_requested, steer_requested = await self._redis.exists(
                self._request_key(*key, intent=ChatControlIntent.CANCEL)
            ), await self._redis.exists(
                self._request_key(*key, intent=ChatControlIntent.STEER)
            )
        except Exception as error:
            raise ChatCancellationUnavailable(
                "chat cancellation coordination unavailable"
            ) from error
        if cancel_requested:
            return ChatControlIntent.CANCEL
        if steer_requested:
            return ChatControlIntent.STEER
        return None

    async def _listen(self, pubsub: object) -> None:
        try:
            while True:
                message = await pubsub.get_message(timeout=1.0)  # type: ignore[attr-defined]
                if not isinstance(message, dict):
                    await asyncio.sleep(0)
                    continue
                parsed = self._parse_message(message.get("data"))
                if parsed is not None:
                    key, intent = parsed
                    await self._interrupt_local(key, intent)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Redis readiness and the cancel endpoint fail closed separately. Do not
            # include payloads or identities in process logs.
            logger.exception("chat_cancellation_listener_failed")

    async def _interrupt_local(
        self,
        key: TaskKey,
        intent: ChatControlIntent,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(key)
            if task is not None and not task.done():
                effective = self._merge_intent(
                    self._requested.get(key),
                    intent,
                )
                self._requested[key] = effective
                acknowledged = self._acknowledged.get(key)
                if acknowledged is not effective:
                    self._acknowledged.pop(key, None)
                    if key not in self._redelivery:
                        self._redelivery[key] = asyncio.create_task(
                            self._redeliver(key, task),
                            name="gerclaw-chat-control-redelivery",
                        )

    async def _redeliver(
        self,
        key: TaskKey,
        task: asyncio.Task[None],
    ) -> None:
        """Repeat a swallowed task cancellation until the owner acknowledges it."""

        try:
            for delay in _REDELIVERY_DELAYS_SECONDS:
                if delay:
                    await asyncio.sleep(delay)
                async with self._lock:
                    if self._tasks.get(key) is not task or task.done():
                        return
                    intent = self._requested.get(key)
                    if intent is None or self._acknowledged.get(key) is intent:
                        return
                task.cancel(
                    "explicit chat cancellation requested"
                    if intent is ChatControlIntent.CANCEL
                    else "immediate chat steer requested"
                )
        except asyncio.CancelledError:
            return
        finally:
            async with self._lock:
                if self._redelivery.get(key) is asyncio.current_task():
                    self._redelivery.pop(key, None)

    @staticmethod
    def _merge_intent(
        current: ChatControlIntent | None,
        incoming: ChatControlIntent,
    ) -> ChatControlIntent:
        """Merge concurrent signals without ever downgrading explicit cancel."""

        if ChatControlIntent.CANCEL in {current, incoming}:
            return ChatControlIntent.CANCEL
        return incoming

    @staticmethod
    def _parse_message(
        raw: object,
    ) -> tuple[TaskKey, ChatControlIntent] | None:
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
        if not isinstance(payload, dict) or frozenset(payload) not in {
            frozenset({"tenant_id", "actor_id", "trace_id"}),
            frozenset({"tenant_id", "actor_id", "trace_id", "intent"}),
        }:
            return None
        values = (payload["tenant_id"], payload["actor_id"], payload["trace_id"])
        if any(not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None for value in values):
            return None
        try:
            intent = ChatControlIntent(payload.get("intent", "cancel"))
        except ValueError:
            return None
        return values, intent

    @staticmethod
    def _request_key(
        tenant_id: str,
        actor_id: str,
        trace_id: str,
        *,
        intent: ChatControlIntent = ChatControlIntent.CANCEL,
    ) -> str:
        return f"gerclaw:chat:{intent.value}:v1:{tenant_id}:{actor_id}:{trace_id}"
