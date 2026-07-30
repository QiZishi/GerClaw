"""Non-blocking online collection and allowlist-only offline export."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime

from gerclaw_api.database.session import Database
from gerclaw_api.modules.agent_harness.evolution_signals import (
    EvolutionSignal,
    EvolutionSignalError,
    EvolutionSignalProjector,
)
from gerclaw_api.repositories.evolution_signal import (
    SqlAlchemyEvolutionSignalRepository,
)

logger = logging.getLogger(__name__)


class DatabaseEvolutionSignalCollector:
    """Reconcile metadata after production facts commit; failures stay non-fatal."""

    def __init__(
        self,
        database: Database,
        *,
        hmac_key: bytes,
        timeout_seconds: float,
        max_pending: int,
        max_concurrent: int,
    ) -> None:
        if (
            timeout_seconds <= 0
            or max_pending < 1
            or max_concurrent < 1
            or max_concurrent > max_pending
        ):
            raise EvolutionSignalError("EVOLUTION_SIGNAL_SCHEDULER_CONFIG_INVALID")
        self._database = database
        self._projector = EvolutionSignalProjector(hmac_key)
        self._timeout_seconds = timeout_seconds
        self._max_pending = max_pending
        self._concurrency = asyncio.Semaphore(max_concurrent)
        self._tasks: set[asyncio.Task[bool]] = set()
        self._closing = False

    async def collect(self, run_id: uuid.UUID) -> EvolutionSignal | None:
        async with self._database.session() as session:
            repository = SqlAlchemyEvolutionSignalRepository(session)
            source = await repository.read_source(run_id)
            if source is None:
                await repository.rollback()
                return None
            signal = self._projector.project(source)
            try:
                await repository.reconcile(signal)
                await repository.commit()
            except BaseException:
                await repository.rollback()
                raise
            return signal

    def schedule(self, run_id: uuid.UUID) -> None:
        """Queue bounded collection without suspending the user-facing task."""

        if self._closing or len(self._tasks) >= self._max_pending:
            logger.warning("EVOLUTION_SIGNAL_COLLECTION_DROPPED")
            return
        task = asyncio.create_task(
            self._collect_safely(run_id),
            name="evolution-signal-collect",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _collect_safely(self, run_id: uuid.UUID) -> bool:
        """Contain timeout/cancellation/failure inside the telemetry task."""

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._concurrency:
                    return await self.collect(run_id) is not None
        except TimeoutError:
            logger.warning("EVOLUTION_SIGNAL_COLLECTION_TIMED_OUT")
            return False
        except asyncio.CancelledError:
            return False
        except Exception:
            # Do not log the Run id, principal, Trace payload, or content. The
            # stable code is enough for an operational counter/alert.
            logger.warning("EVOLUTION_SIGNAL_COLLECTION_FAILED")
            return False

    async def wait_pending(self) -> None:
        """Test/shutdown barrier; request paths must never call this method."""

        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        """Stop accepting work and finish already bounded tasks before DB disposal."""

        self._closing = True
        await self.wait_pending()


class EvolutionSignalExporter:
    """Produce bounded JSONL containing exactly the public signal contract."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def page(
        self,
        *,
        after_occurred_at: datetime | None = None,
        after_fingerprint: str | None = None,
        limit: int = 500,
    ) -> tuple[EvolutionSignal, ...]:
        async with self._database.session() as session:
            repository = SqlAlchemyEvolutionSignalRepository(session)
            try:
                signals = await repository.list_signals(
                    after_occurred_at=after_occurred_at,
                    after_fingerprint=after_fingerprint,
                    limit=limit,
                )
            finally:
                await repository.rollback()
            return signals

    async def jsonl_page(
        self,
        *,
        after_occurred_at: datetime | None = None,
        after_fingerprint: str | None = None,
        limit: int = 500,
    ) -> bytes:
        signals = await self.page(
            after_occurred_at=after_occurred_at,
            after_fingerprint=after_fingerprint,
            limit=limit,
        )
        try:
            text = "\n".join(
                json.dumps(
                    signal.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                for signal in signals
            )
        except (TypeError, ValueError) as error:
            raise EvolutionSignalError("EVOLUTION_SIGNAL_EXPORT_ENCODING_FAILED") from error
        return (text + ("\n" if text else "")).encode("utf-8")
