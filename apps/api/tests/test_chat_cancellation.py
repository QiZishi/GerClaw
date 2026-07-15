"""Replica-safe chat cancellation registry tests."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
)


class _FakePubSub:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.closed = False

    async def subscribe(self, _channel: str) -> None:
        return None

    async def unsubscribe(self, _channel: str) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True

    async def get_message(self, **kwargs: object) -> dict[str, object] | None:
        wait_seconds = float(cast(float, kwargs["timeout"]))
        try:
            return await asyncio.wait_for(self.messages.get(), timeout=wait_seconds)
        except TimeoutError:
            return None


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self.redis = redis
        self.operations: list[tuple[str, tuple[object, ...]]] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def set(self, *args: object, **kwargs: object) -> None:
        self.operations.append(("set", (*args, kwargs)))

    def publish(self, *args: object) -> None:
        self.operations.append(("publish", args))

    async def execute(self) -> None:
        for operation, args in self.operations:
            if operation == "set":
                key, value, kwargs = args
                await self.redis.set(str(key), str(value), **cast(dict[str, Any], kwargs))
            else:
                channel, payload = args
                await self.redis.publish(str(channel), str(payload))


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.subscribers: list[_FakePubSub] = []

    def pubsub(self, **_kwargs: object) -> _FakePubSub:
        pubsub = _FakePubSub()
        self.subscribers.append(pubsub)
        return pubsub

    def pipeline(self, **_kwargs: object) -> _FakePipeline:
        return _FakePipeline(self)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def set(self, key: str, value: str, **_kwargs: object) -> None:
        self.values[key] = value

    async def publish(self, _channel: str, payload: str) -> int:
        for subscriber in self.subscribers:
            subscriber.messages.put_nowait({"data": payload})
        return len(self.subscribers)


async def _never() -> None:
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_cancellation_fans_out_to_the_task_on_another_replica() -> None:
    redis = _FakeRedis()
    first = ChatCancellationRegistry(cast(Redis, redis))
    second = ChatCancellationRegistry(cast(Redis, redis))
    await first.start()
    await second.start()
    task = asyncio.create_task(_never())
    await second.register(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0001",
        task=task,
    )

    await first.request_cancel(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0001",
    )
    result = (await asyncio.gather(task, return_exceptions=True))[0]

    assert isinstance(result, asyncio.CancelledError)
    assert await second.is_cancel_requested(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0001",
    )
    await second.unregister(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0001",
        task=task,
    )
    assert second._requested == set()
    await first.aclose()
    await second.aclose()
    assert all(subscriber.closed for subscriber in redis.subscribers)


@pytest.mark.asyncio
async def test_registration_honors_a_cancel_request_that_won_the_startup_race() -> None:
    redis = _FakeRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    await registry.start()
    await registry.request_cancel(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0002",
    )
    task = asyncio.create_task(_never())

    await registry.register(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0002",
        task=task,
    )
    result = (await asyncio.gather(task, return_exceptions=True))[0]

    assert isinstance(result, asyncio.CancelledError)
    assert await registry.is_cancel_requested(
        tenant_id="tenant_public0001",
        actor_id="usr_patient00000001",
        trace_id="trace_cancel_registry_0002",
    )
    await registry.aclose()


@pytest.mark.asyncio
async def test_registration_fails_closed_when_redis_cannot_check_the_race() -> None:
    class _FailingRedis(_FakeRedis):
        async def exists(self, key: str) -> int:
            del key
            raise ConnectionError("injected")

    registry = ChatCancellationRegistry(cast(Redis, _FailingRedis()))
    task = asyncio.create_task(_never())
    with pytest.raises(ChatCancellationUnavailable):
        await registry.register(
            tenant_id="tenant_public0001",
            actor_id="usr_patient00000001",
            trace_id="trace_cancel_registry_0003",
            task=task,
        )
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_final_cancellation_fence_fails_closed_when_redis_is_unavailable() -> None:
    class _FailingRedis(_FakeRedis):
        async def exists(self, key: str) -> int:
            del key
            raise ConnectionError("injected")

    registry = ChatCancellationRegistry(cast(Redis, _FailingRedis()))
    with pytest.raises(ChatCancellationUnavailable):
        await registry.is_cancel_requested(
            tenant_id="tenant_public0001",
            actor_id="usr_patient00000001",
            trace_id="trace_cancel_registry_0004",
        )


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        "{}",
        (
            '{"tenant_id":"unsafe space","actor_id":"usr_patient00000001",'
            '"trace_id":"trace_ok00000001"}'
        ),
        '{"tenant_id":"tenant_public0001","actor_id":"usr_patient00000001"}',
    ],
)
def test_cancellation_listener_rejects_malformed_messages(payload: object) -> None:
    assert ChatCancellationRegistry._parse_message(payload) is None
