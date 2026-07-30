"""Persistence boundary for current, metadata-only evolution signals."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import (
    AgentRun,
    EvolutionSignalRecord,
    ExecutionTrace,
    RunFeedbackState,
    TraceEvent,
)
from gerclaw_api.domain.chat_error_codes import (
    CHAT_CANCELLATION_ERROR_CODE,
    CHAT_ERROR_CODES,
    CHAT_FALLBACK_ERROR_CODE,
)
from gerclaw_api.modules.agent_harness.context_snapshot.persisted import PersistedRunPlan
from gerclaw_api.modules.agent_harness.evolution_signals import (
    EvolutionSignal,
    EvolutionSignalError,
    EvolutionSignalSource,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.catalog import (
    GERCLAW_CAPABILITY_MANIFESTS,
)

_SIGNAL_STATUSES = frozenset(
    {
        "waiting_for_user",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "interrupted",
    }
)
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_CAPABILITY_IDS = frozenset(item.capability_id for item in GERCLAW_CAPABILITY_MANIFESTS)


class SqlAlchemyEvolutionSignalRepository:
    """Read only allowlisted fields and reconcile one current row per Run."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_source(self, run_id: uuid.UUID) -> EvolutionSignalSource | None:
        run = cast(
            AgentRun | None,
            await self._session.scalar(select(AgentRun).where(AgentRun.id == run_id)),
        )
        if run is None or run.status not in _SIGNAL_STATUSES:
            return None
        try:
            plan = PersistedRunPlan.model_validate(run.plan)
        except ValueError:
            # Legacy Runs can predate run-plan-v1. Never inspect or infer from
            # their free-form payload; retain outcome metrics with empty IDs.
            capability_ids: tuple[str, ...] = ()
            skill_ids: tuple[str, ...] = ()
        else:
            capability_ids = plan.capability_selection.ids
            skill_ids = tuple(plan.loaded_skill_ids)

        trace = cast(
            ExecutionTrace | None,
            await self._session.scalar(
                select(ExecutionTrace).where(
                    ExecutionTrace.tenant_id == run.tenant_id,
                    ExecutionTrace.trace_id == run.trace_id,
                )
            ),
        )
        feedback = cast(
            RunFeedbackState | None,
            await self._session.scalar(
                select(RunFeedbackState).where(
                    RunFeedbackState.run_id == run.id,
                    RunFeedbackState.tenant_id == run.tenant_id,
                    RunFeedbackState.actor_id == run.actor_id,
                )
            ),
        )
        payloads = (
            await self._session.scalars(
                select(TraceEvent.payload).where(
                    TraceEvent.tenant_id == run.tenant_id,
                    TraceEvent.trace_id == run.trace_id,
                    TraceEvent.event_type == "model.call",
                )
            )
        ).all()
        input_tokens = 0
        output_tokens = 0
        for payload in payloads:
            # Trace payloads can contain provider metadata. Only these two
            # validated numeric counters may cross the signal projection.
            raw_input = payload.get("input_tokens")
            raw_output = payload.get("output_tokens")
            if isinstance(raw_input, int) and not isinstance(raw_input, bool) and raw_input >= 0:
                input_tokens += raw_input
            if isinstance(raw_output, int) and not isinstance(raw_output, bool) and raw_output >= 0:
                output_tokens += raw_output

        occurred_at = run.completed_at or run.interrupted_at or run.updated_at
        duration_ms = trace.duration_ms if trace is not None else None
        if duration_ms is None:
            duration_ms = max(0, int((occurred_at - run.started_at).total_seconds() * 1_000))
        raw_error = trace.error_code.upper() if trace is not None and trace.error_code else None
        error_code = (
            raw_error if raw_error is not None and _ERROR_CODE.fullmatch(raw_error) else None
        )
        if error_code not in CHAT_ERROR_CODES:
            error_code = (
                CHAT_CANCELLATION_ERROR_CODE
                if run.status == "cancelled"
                else CHAT_FALLBACK_ERROR_CODE
            )
        if run.status not in {"failed", "cancelled"}:
            error_code = None
        if any(item not in _CAPABILITY_IDS for item in capability_ids):
            raise EvolutionSignalError("EVOLUTION_SIGNAL_CAPABILITY_NOT_ALLOWLISTED")

        return EvolutionSignalSource(
            run_id=run.id,
            route=run.route,
            run_status=run.status,
            error_code=error_code,
            capability_ids=capability_ids,
            skill_ids=skill_ids,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=max(0, duration_ms),
            feedback_value=feedback.value if feedback is not None else 0,
            feedback_revision=feedback.revision if feedback is not None else 0,
            occurred_at=occurred_at,
        )

    async def reconcile(self, signal: EvolutionSignal) -> None:
        values = signal.model_dump(mode="python")
        statement = insert(EvolutionSignalRecord).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[EvolutionSignalRecord.run_fingerprint],
            set_={
                **{
                    key: getattr(statement.excluded, key)
                    for key in values
                    if key != "run_fingerprint"
                },
                "updated_at": func.now(),
            },
            where=and_(
                statement.excluded.occurred_at >= EvolutionSignalRecord.occurred_at,
                statement.excluded.feedback_revision >= EvolutionSignalRecord.feedback_revision,
            ),
        )
        await self._session.execute(statement)

    async def list_signals(
        self,
        *,
        after_occurred_at: datetime | None,
        after_fingerprint: str | None,
        limit: int,
    ) -> tuple[EvolutionSignal, ...]:
        if limit < 1 or limit > 1_000:
            raise EvolutionSignalError("EVOLUTION_SIGNAL_EXPORT_LIMIT_INVALID")
        if (after_occurred_at is None) != (after_fingerprint is None):
            raise EvolutionSignalError("EVOLUTION_SIGNAL_EXPORT_CURSOR_INVALID")
        statement = select(EvolutionSignalRecord)
        if after_occurred_at is not None and after_fingerprint is not None:
            statement = statement.where(
                or_(
                    EvolutionSignalRecord.occurred_at > after_occurred_at,
                    and_(
                        EvolutionSignalRecord.occurred_at == after_occurred_at,
                        EvolutionSignalRecord.run_fingerprint > after_fingerprint,
                    ),
                )
            )
        records = (
            await self._session.scalars(
                statement.order_by(
                    EvolutionSignalRecord.occurred_at,
                    EvolutionSignalRecord.run_fingerprint,
                ).limit(limit)
            )
        ).all()
        return tuple(
            EvolutionSignal.model_validate(
                {
                    "schema_version": record.schema_version,
                    "run_fingerprint": record.run_fingerprint,
                    "route": record.route,
                    "run_status": record.run_status,
                    "error_code": record.error_code,
                    "risk_level": record.risk_level,
                    "capability_ids": tuple(record.capability_ids),
                    "skill_ids": tuple(record.skill_ids),
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "duration_ms": record.duration_ms,
                    "feedback_value": record.feedback_value,
                    "feedback_revision": record.feedback_revision,
                    "occurred_at": record.occurred_at,
                }
            )
            for record in records
        )

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
