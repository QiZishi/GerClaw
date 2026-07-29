"""Actor/session-scoped request-local result reuse."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import PluginRuntimeError

T = TypeVar("T")


class SharedResultKind(StrEnum):
    ATTACHMENT_PROJECTION = "attachment_projection"
    CLINICAL_OBSERVATION = "clinical_observation"
    LOCAL_EVIDENCE = "local_evidence"


class SharedResultScope(BaseModel):
    """Exact private scope; it is never serialized into a public result ref."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)


class SharedResultRef(BaseModel):
    """Opaque reference with content-free reuse metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    result_ref: str = Field(pattern=r"^shared_[A-Za-z0-9_-]{20,64}$")
    kind: SharedResultKind
    producer: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    reusable_by: tuple[str, ...] = Field(min_length=1, max_length=20)


@dataclass(frozen=True, slots=True)
class SharedResult[T]:
    value: T
    reference: SharedResultRef
    reused: bool


@dataclass(frozen=True, slots=True)
class _StoredResult[T]:
    scope: SharedResultScope
    value: T
    reference: SharedResultRef


class TurnSharedResultStore:
    """Keep private payloads in one turn and expose only opaque references."""

    def __init__(self, scope: SharedResultScope) -> None:
        self._scope = scope
        self._entries: dict[str, _StoredResult[object]] = {}
        self._keys: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        *,
        key: str,
        kind: SharedResultKind,
        producer: str,
        reusable_by: tuple[str, ...],
        factory: Callable[[], Awaitable[T]],
    ) -> SharedResult[T]:
        if not key or len(key) > 128:
            raise PluginRuntimeError("SHARED_RESULT_KEY_INVALID")
        normalized_consumers = tuple(dict.fromkeys(reusable_by))
        if not normalized_consumers:
            raise PluginRuntimeError("SHARED_RESULT_CONSUMERS_REQUIRED")
        async with self._lock:
            existing_ref = self._keys.get(key)
            if existing_ref is not None:
                stored = self._entries[existing_ref]
                self._validate_contract(
                    stored.reference,
                    kind=kind,
                    producer=producer,
                    reusable_by=normalized_consumers,
                )
                return SharedResult(
                    value=stored.value,  # type: ignore[arg-type]
                    reference=stored.reference,
                    reused=True,
                )
            value = await factory()
            reference = SharedResultRef(
                result_ref=f"shared_{secrets.token_urlsafe(18)}",
                kind=kind,
                producer=producer,
                reusable_by=normalized_consumers,
            )
            self._entries[reference.result_ref] = _StoredResult(
                scope=self._scope,
                value=value,
                reference=reference,
            )
            self._keys[key] = reference.result_ref
            return SharedResult(value=value, reference=reference, reused=False)

    def resolve(
        self,
        reference: SharedResultRef,
        *,
        scope: SharedResultScope,
        consumer: str,
    ) -> object:
        stored = self._entries.get(reference.result_ref)
        if stored is None or stored.reference != reference:
            raise PluginRuntimeError("SHARED_RESULT_UNKNOWN")
        if stored.scope != scope:
            raise PluginRuntimeError("SHARED_RESULT_SCOPE_MISMATCH")
        if consumer not in reference.reusable_by:
            raise PluginRuntimeError("SHARED_RESULT_CONSUMER_DENIED")
        return stored.value

    @staticmethod
    def _validate_contract(
        reference: SharedResultRef,
        *,
        kind: SharedResultKind,
        producer: str,
        reusable_by: tuple[str, ...],
    ) -> None:
        if (
            reference.kind is not kind
            or reference.producer != producer
            or reference.reusable_by != reusable_by
        ):
            raise PluginRuntimeError("SHARED_RESULT_KEY_CONTRACT_MISMATCH")
