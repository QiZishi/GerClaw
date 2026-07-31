"""Replica-safe chat cancellation registry tests."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from gerclaw_api.services.chat_cancellation import (
    ChatCancellationRegistry,
    ChatCancellationUnavailable,
    ChatControlIntent,
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
async def test_control_redelivery_interrupts_a_task_that_swallows_the_first_signal() -> None:
    redis = _FakeRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    first_signal = asyncio.Event()

    async def cancellation_resistant() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            first_signal.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(cancellation_resistant())
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_redelivery_0001",
    }
    await registry.register(task=task, **key)
    await registry.request_steer(**key)
    await asyncio.wait_for(first_signal.wait(), timeout=1)
    result = (
        await asyncio.wait_for(
            asyncio.gather(task, return_exceptions=True),
            timeout=2,
        )
    )[0]

    assert isinstance(result, asyncio.CancelledError)
    await registry.unregister(task=task, **key)
    await registry.aclose()


@pytest.mark.asyncio
async def test_shutdown_drains_detached_owner_before_closing_coordination() -> None:
    redis = _FakeRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    await registry.start()
    release = asyncio.Event()
    task = asyncio.create_task(release.wait())
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_shutdown_drain_0001",
    }
    await registry.register(task=task, **key)

    closing = asyncio.create_task(registry.aclose())
    await asyncio.sleep(0)
    assert not closing.done()
    assert not redis.subscribers[0].closed

    release.set()
    await closing

    assert task.done()
    assert registry._tasks == {}
    assert redis.subscribers[0].closed
    late = asyncio.create_task(_never())
    with pytest.raises(ChatCancellationUnavailable):
        await registry.register(task=late, **key)
    late.cancel()
    await asyncio.gather(late, return_exceptions=True)


@pytest.mark.asyncio
async def test_acknowledgement_stops_redelivery_during_terminal_cleanup() -> None:
    redis = _FakeRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_acknowledge_0001",
    }

    async def acknowledged_cleanup() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            registry.acknowledge_control(**key)
            cleanup_started.set()
        await cleanup_release.wait()

    task = asyncio.create_task(acknowledged_cleanup())
    await registry.register(task=task, **key)
    await registry.request_cancel(**key)
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)
    await asyncio.sleep(0.4)
    assert not task.done()
    cleanup_release.set()
    await task

    await registry.unregister(task=task, **key)
    await registry.aclose()


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
    assert second._requested == {}
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
async def test_steer_fans_out_without_becoming_a_cancel_intent() -> None:
    redis = _FakeRedis()
    sender = ChatCancellationRegistry(cast(Redis, redis))
    owner = ChatCancellationRegistry(cast(Redis, redis))
    await sender.start()
    await owner.start()
    task = asyncio.create_task(_never())
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_steer_registry_0001",
    }
    await owner.register(task=task, **key)

    await sender.request_steer(**key)
    result = (await asyncio.gather(task, return_exceptions=True))[0]

    assert isinstance(result, asyncio.CancelledError)
    assert await owner.is_steer_requested(**key)
    assert not await owner.is_cancel_requested(**key)
    assert await owner.is_interruption_requested(**key)
    await owner.unregister(task=task, **key)
    await sender.aclose()
    await owner.aclose()


@pytest.mark.asyncio
async def test_explicit_cancel_takes_precedence_over_steer() -> None:
    redis = _FakeRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_control_precedence_0001",
    }

    await registry.request_steer(**key)
    await registry.request_cancel(**key)

    assert await registry.control_intent(**key) is ChatControlIntent.CANCEL
    assert await registry.is_cancel_requested(**key)
    assert not await registry.is_steer_requested(**key)


@pytest.mark.asyncio
async def test_delivered_local_steer_remains_a_final_fence_during_redis_outage() -> None:
    class _FailAfterSignalRedis(_FakeRedis):
        fail_reads = False

        async def exists(self, key: str) -> int:
            if self.fail_reads:
                raise ConnectionError("injected")
            return await super().exists(key)

    redis = _FailAfterSignalRedis()
    registry = ChatCancellationRegistry(cast(Redis, redis))
    task = asyncio.create_task(_never())
    key = {
        "tenant_id": "tenant_public0001",
        "actor_id": "usr_patient00000001",
        "trace_id": "trace_local_steer_fence_0001",
    }
    await registry.register(task=task, **key)

    await registry.request_steer(**key)
    redis.fail_reads = True

    assert await registry.control_intent(**key) is ChatControlIntent.STEER
    assert await registry.is_steer_requested(**key)
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stale_steer_read_cannot_downgrade_concurrent_local_cancel() -> None:
    class _BarrierRegistry(ChatCancellationRegistry):
        block_reads = False

        def __init__(self, redis: Redis) -> None:
            super().__init__(redis)
            self.read_started = asyncio.Event()
            self.release_read = asyncio.Event()

        async def _read_intent(
            self,
            key: tuple[str, str, str],
        ) -> ChatControlIntent | None:
            if not self.block_reads:
                return await super()._read_intent(key)
            self.read_started.set()
            await self.release_read.wait()
            return ChatControlIntent.STEER

    redis = _FakeRedis()
    registry = _BarrierRegistry(cast(Redis, redis))
    task = asyncio.create_task(_never())
    key = (
        "tenant_public0001",
        "usr_patient00000001",
        "trace_control_merge_0001",
    )
    await registry.register(
        tenant_id=key[0],
        actor_id=key[1],
        trace_id=key[2],
        task=task,
    )
    registry.block_reads = True

    probe = asyncio.create_task(
        registry.control_intent(
            tenant_id=key[0],
            actor_id=key[1],
            trace_id=key[2],
        )
    )
    await registry.read_started.wait()
    await registry._interrupt_local(key, ChatControlIntent.CANCEL)
    registry.release_read.set()

    assert await probe is ChatControlIntent.CANCEL
    assert registry._requested[key] is ChatControlIntent.CANCEL
    await asyncio.gather(task, return_exceptions=True)


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
        (
            '{"tenant_id":"tenant_public0001","actor_id":"usr_patient00000001",'
            '"trace_id":"trace_ok00000001","intent":"unknown"}'
        ),
    ],
)
def test_cancellation_listener_rejects_malformed_messages(payload: object) -> None:
    assert ChatCancellationRegistry._parse_message(payload) is None
