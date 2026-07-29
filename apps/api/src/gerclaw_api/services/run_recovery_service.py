"""Lease-aware startup reconciliation for orphaned Agent runs."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from gerclaw_api.database.session import Database
from gerclaw_api.modules.agent_harness.run_lifecycle import RunTransitionError
from gerclaw_api.repositories.agent_run import SqlAlchemyAgentRunRepository
from gerclaw_api.repositories.run_recovery import SqlAlchemyRunRecoveryRepository
from gerclaw_api.services.agent_run_service import AgentRunNotFoundError, AgentRunService
from gerclaw_api.services.session_lease import (
    SessionLease,
    SessionLeaseLostError,
    SessionLeaseUnavailableError,
)


class RunRecoveryUnavailableError(RuntimeError):
    """Raised when lease state cannot be verified safely."""


class StaleAgentRunReconciler:
    """Interrupt only unfinished runs whose cross-replica lease is absent."""

    def __init__(
        self,
        database: Database,
        redis: Redis,
        *,
        batch_size: int,
        guard_ttl_seconds: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._database = database
        self._lease = SessionLease(redis, ttl_seconds=guard_ttl_seconds)
        self._batch_size = batch_size

    async def reconcile(self) -> int:
        """Return the number of runs durably moved to interrupted."""

        interrupted = 0
        after_run_id: uuid.UUID | None = None
        while True:
            async with self._database.session() as session:
                candidates = await SqlAlchemyRunRecoveryRepository(session).list_candidates(
                    after_run_id=after_run_id,
                    limit=self._batch_size,
                )
            if not candidates:
                return interrupted
            for candidate in candidates:
                try:
                    async with self._lease.recover_orphan(
                        tenant_id=candidate.tenant_id,
                        session_id=candidate.conversation_id,
                    ) as recovery_guard:
                        if recovery_guard is None:
                            continue
                        try:
                            async with self._database.session() as session:
                                repository = SqlAlchemyAgentRunRepository(session)
                                await AgentRunService(repository).interrupt_owned(
                                    candidate.run_id,
                                    tenant_id=candidate.tenant_id,
                                    actor_id=candidate.actor_id,
                                    commit=False,
                                )
                                await recovery_guard.assert_owned()
                                await repository.commit()
                        except (AgentRunNotFoundError, RunTransitionError):
                            # A concurrent cancel or completion won before the
                            # recovery guard was acquired.
                            continue
                except (SessionLeaseLostError, SessionLeaseUnavailableError) as error:
                    raise RunRecoveryUnavailableError(
                        "cannot verify active Agent run leases"
                    ) from error
                interrupted += 1
            after_run_id = candidates[-1].run_id
            if len(candidates) < self._batch_size:
                return interrupted
