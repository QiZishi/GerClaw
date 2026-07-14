"""Atomic rate limiter behavior and fail-closed policy tests."""

import pytest
from redis.exceptions import RedisError

from gerclaw_api.services.rate_limit import (
    RateLimiter,
    RateLimitExceeded,
    RateLimitUnavailable,
)


class FakeRedis:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = [1, 60_000] if result is None else result
        self.error = error

    async def eval(self, *args: object) -> object:
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_rate_limiter_accepts_then_rejects_with_retry_after() -> None:
    limiter = RateLimiter(FakeRedis(), limit=2, window_seconds=60)  # type: ignore[arg-type]
    await limiter.check(tenant_id="tenant_public0001", actor_id="usr_patient_rate0001")

    limited = RateLimiter(FakeRedis([3, 1_001]), limit=2, window_seconds=60)  # type: ignore[arg-type]
    with pytest.raises(RateLimitExceeded) as error:
        await limited.check(tenant_id="tenant_public0001", actor_id="usr_patient_rate0001")
    assert error.value.retry_after_seconds == 2


@pytest.mark.asyncio
async def test_rate_limiter_fails_closed_on_redis_errors_or_invalid_results() -> None:
    unavailable = RateLimiter(
        FakeRedis(error=RedisError("down")),
        limit=2,
        window_seconds=60,  # type: ignore[arg-type]
    )
    with pytest.raises(RateLimitUnavailable):
        await unavailable.check(tenant_id="tenant_public0001", actor_id="usr_patient_rate0001")

    invalid = RateLimiter(FakeRedis("invalid"), limit=2, window_seconds=60)  # type: ignore[arg-type]
    with pytest.raises(RateLimitUnavailable):
        await invalid.check(tenant_id="tenant_public0001", actor_id="usr_patient_rate0001")
