"""Redis lease fencing and failure behavior."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import pytest
from redis.exceptions import RedisError

from gerclaw_api.services.session_lease import (
    SessionBusyError,
    SessionLease,
    SessionLeaseLostError,
    SessionLeaseUnavailableError,
)


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail_eval = False
        self.renew_results: list[int] = []

    async def eval(self, script: str, key_count: int, *args: str) -> int:
        if self.fail_eval:
            raise RedisError("unavailable")
        keys = args[:key_count]
        values = args[key_count:]
        if "'NX', 'EX'" in script:
            first_key, second_key = keys
            owner_value = values[0]
            if "exists', KEYS[2]" in script:
                target_key, exclusion_key = first_key, second_key
            else:
                exclusion_key, target_key = first_key, second_key
            if exclusion_key in self.values or target_key in self.values:
                return 0
            self.values[target_key] = owner_value
            return 1
        key = keys[0]
        token = values[0]
        if "pexpire" in script:
            if self.renew_results:
                return self.renew_results.pop(0)
            return int(self.values.get(key) == token)
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_lease_acquires_rejects_competitor_and_releases_owner() -> None:
    redis = _Redis()
    lease = SessionLease(cast(Any, redis), ttl_seconds=60)
    session_id = uuid.uuid4()
    key = f"gerclaw:chat:lease:tenant_public0001:{session_id}"
    assert key == SessionLease.key_for(
        tenant_id="tenant_public0001",
        session_id=session_id,
    )

    async with lease.acquire(
        tenant_id="tenant_public0001", session_id=session_id, fencing_token=1
    ) as guard:
        assert key in redis.values
        assert guard.fencing_token == 1
        await guard.assert_owned()
        with pytest.raises(SessionBusyError):
            async with lease.acquire(
                tenant_id="tenant_public0001", session_id=session_id, fencing_token=2
            ):
                pytest.fail("competitor must not enter")
    assert key not in redis.values


@pytest.mark.asyncio
async def test_lease_fails_closed_when_redis_cannot_coordinate() -> None:
    redis = _Redis()
    redis.fail_eval = True
    lease = SessionLease(cast(Any, redis), ttl_seconds=60)
    with pytest.raises(SessionLeaseUnavailableError):
        async with lease.acquire(
            tenant_id="tenant_public0001", session_id=uuid.uuid4(), fencing_token=1
        ):
            pytest.fail("unavailable Redis must not permit execution")


@pytest.mark.asyncio
async def test_recovery_guard_and_worker_lease_exclude_each_other() -> None:
    redis = _Redis()
    lease = SessionLease(cast(Any, redis), ttl_seconds=60)
    session_id = uuid.uuid4()
    recovery_key = SessionLease.recovery_key_for(
        tenant_id="tenant_public0001",
        session_id=session_id,
    )

    async with lease.recover_orphan(
        tenant_id="tenant_public0001",
        session_id=session_id,
    ) as owns_recovery:
        assert owns_recovery
        assert recovery_key in redis.values
        with pytest.raises(SessionBusyError):
            async with lease.acquire(
                tenant_id="tenant_public0001",
                session_id=session_id,
                fencing_token=2,
            ):
                pytest.fail("worker must not enter during orphan reconciliation")
    assert recovery_key not in redis.values

    async with lease.acquire(
        tenant_id="tenant_public0001",
        session_id=session_id,
        fencing_token=3,
    ), lease.recover_orphan(
        tenant_id="tenant_public0001",
        session_id=session_id,
    ) as owns_recovery:
        assert not owns_recovery


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_failure", [False, True])
async def test_renewal_loss_cancels_owner(redis_failure: bool) -> None:
    redis = _Redis()
    redis.fail_eval = redis_failure
    redis.renew_results = [1, 0]
    lease = SessionLease(cast(Any, redis), ttl_seconds=0)
    blocked = asyncio.Event()

    async def owner() -> None:
        await blocked.wait()

    owner_task = asyncio.create_task(owner())
    await lease._renew(key="lease", owner_value="owner", owner_task=owner_task)
    result = (await asyncio.gather(owner_task, return_exceptions=True))[0]
    assert isinstance(result, asyncio.CancelledError)


@pytest.mark.asyncio
async def test_guard_fails_closed_after_successor_replaces_owner() -> None:
    redis = _Redis()
    lease = SessionLease(cast(Any, redis), ttl_seconds=60)
    session_id = uuid.uuid4()
    key = f"gerclaw:chat:lease:tenant_public0001:{session_id}"

    async with lease.acquire(
        tenant_id="tenant_public0001", session_id=session_id, fencing_token=41
    ) as guard:
        redis.values[key] = "42:successor"
        with pytest.raises(SessionLeaseLostError):
            await guard.assert_owned()


@pytest.mark.asyncio
async def test_guard_and_token_validation_fail_closed() -> None:
    redis = _Redis()
    redis.fail_eval = True
    lease = SessionLease(cast(Any, redis), ttl_seconds=60)
    session_id = uuid.uuid4()
    redis.fail_eval = False
    async with lease.acquire(
        tenant_id="tenant_public0001", session_id=session_id, fencing_token=1
    ) as guard:
        redis.fail_eval = True
        with pytest.raises(SessionLeaseUnavailableError):
            await guard.assert_owned()
    with pytest.raises(ValueError, match="positive"):
        async with lease.acquire(
            tenant_id="tenant_public0001", session_id=session_id, fencing_token=0
        ):
            pytest.fail("invalid fencing token must not acquire")
