"""Encrypted Runtime checkpoint persistence with strict version-bound recovery."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import RuntimeApproval, RuntimeCheckpointRecord
from gerclaw_api.modules.runtime.models import RuntimeCheckpoint


class CheckpointNotFoundError(LookupError):
    """Checkpoint is absent or outside the verified principal boundary."""


class CheckpointConflictError(RuntimeError):
    """Checkpoint is stale, terminal, corrupt, or version-incompatible."""


def _state_fingerprint(state: Mapping[str, object]) -> str:
    canonical = json.dumps(
        state,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class SqlAlchemyCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        checkpoint: RuntimeCheckpoint,
        *,
        tenant_id: str,
        actor_id: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> RuntimeCheckpointRecord:
        approval_exists = await self._session.scalar(
            select(RuntimeApproval.id).where(
                RuntimeApproval.id == approval_id,
                RuntimeApproval.tenant_id == tenant_id,
                RuntimeApproval.requester_actor_id == actor_id,
                RuntimeApproval.user_id == user_id,
                RuntimeApproval.session_id == session_id,
                RuntimeApproval.trace_id == checkpoint.trace_id,
            )
        )
        if approval_exists is None:
            raise CheckpointNotFoundError("approval not found for checkpoint")
        existing = await self._session.scalar(
            select(RuntimeCheckpointRecord).where(
                RuntimeCheckpointRecord.tenant_id == tenant_id,
                RuntimeCheckpointRecord.trace_id == checkpoint.trace_id,
                RuntimeCheckpointRecord.sequence == checkpoint.sequence,
            )
        )
        fingerprint = _state_fingerprint(checkpoint.state)
        if existing is not None:
            if existing.state_fingerprint != fingerprint:
                raise CheckpointConflictError("checkpoint sequence payload differs")
            return existing
        record = RuntimeCheckpointRecord(
            id=checkpoint.checkpoint_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            user_id=user_id,
            session_id=session_id,
            trace_id=checkpoint.trace_id,
            approval_id=approval_id,
            sequence=checkpoint.sequence,
            schema_version=checkpoint.schema_version,
            policy_version=checkpoint.policy_version,
            workflow_version=checkpoint.workflow_version,
            capability_versions=checkpoint.capability_versions,
            state=checkpoint.state,
            state_fingerprint=fingerprint,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def load_parked(
        self,
        checkpoint_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        schema_version: str,
        policy_version: str,
        workflow_version: str,
        capability_versions: dict[str, str],
    ) -> RuntimeCheckpointRecord:
        record = await self._session.scalar(
            select(RuntimeCheckpointRecord)
            .where(
                RuntimeCheckpointRecord.id == checkpoint_id,
                RuntimeCheckpointRecord.tenant_id == tenant_id,
                RuntimeCheckpointRecord.actor_id == actor_id,
            )
            .with_for_update()
        )
        if record is None:
            raise CheckpointNotFoundError("checkpoint not found")
        if record.status != "parked":
            raise CheckpointConflictError("checkpoint is already terminal")
        if _state_fingerprint(record.state) != record.state_fingerprint:
            raise CheckpointConflictError("checkpoint state failed integrity validation")
        expected = (
            schema_version,
            policy_version,
            workflow_version,
            capability_versions,
        )
        actual = (
            record.schema_version,
            record.policy_version,
            record.workflow_version,
            record.capability_versions,
        )
        if actual != expected:
            raise CheckpointConflictError("checkpoint runtime versions are incompatible")
        return record

    async def mark_resumed(
        self,
        checkpoint_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        expected_revision: int,
        now: datetime | None = None,
    ) -> RuntimeCheckpointRecord:
        record = await self._session.scalar(
            select(RuntimeCheckpointRecord)
            .where(
                RuntimeCheckpointRecord.id == checkpoint_id,
                RuntimeCheckpointRecord.tenant_id == tenant_id,
                RuntimeCheckpointRecord.actor_id == actor_id,
            )
            .with_for_update()
        )
        if record is None:
            raise CheckpointNotFoundError("checkpoint not found")
        if record.status != "parked" or record.revision != expected_revision:
            raise CheckpointConflictError("checkpoint revision is stale or already terminal")
        record.status = "resumed"
        record.resumed_at = now or datetime.now(UTC)
        record.revision += 1
        await self._session.flush()
        await self._session.refresh(record)
        return record
