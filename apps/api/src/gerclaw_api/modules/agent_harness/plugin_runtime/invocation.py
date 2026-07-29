"""Validated dispatch from governed manifests to injected owner entrypoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gerclaw_api.modules.agent_harness.plugin_runtime.catalog import (
    GovernedCapabilityCatalog,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import (
    CapabilityEntrypoint,
    CapabilityResult,
    PluginManifest,
    PluginRuntimeError,
)
from gerclaw_api.security import JsonValue


class CapabilityInvocationContext(BaseModel):
    """Content-free, owner-scoped context accepted by every owner adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=128)


OwnerCapabilityHandler = Callable[
    [CapabilityInvocationContext, str],
    Awaitable[CapabilityResult],
]


class GovernedCapabilityRuntime:
    """Invoke only the exact owner callback declared by an allowlisted manifest."""

    def __init__(
        self,
        *,
        catalog: GovernedCapabilityCatalog,
        handlers: Mapping[CapabilityEntrypoint, OwnerCapabilityHandler],
    ) -> None:
        self._catalog = catalog
        self._handlers = dict(handlers)

    def manifests(self) -> tuple[PluginManifest, ...]:
        return self._catalog.manifests()

    async def invoke(
        self,
        capability_id: str,
        payload: dict[str, JsonValue],
    ) -> CapabilityResult:
        manifest = self._catalog.resolve(capability_id)
        if manifest.entrypoint is None:  # pragma: no cover - catalog invariant
            raise PluginRuntimeError(f"CAPABILITY_ENTRYPOINT_MISSING:{capability_id}")
        handler = self._handlers.get(manifest.entrypoint)
        if handler is None:
            raise PluginRuntimeError(f"CAPABILITY_OWNER_UNAVAILABLE:{capability_id}")
        try:
            context = CapabilityInvocationContext.model_validate(payload)
        except ValidationError as error:
            raise PluginRuntimeError(f"CAPABILITY_INPUT_INVALID:{capability_id}") from error
        result = await handler(context, capability_id)
        if result.capability_id != capability_id:
            raise PluginRuntimeError(f"CAPABILITY_OWNER_RESULT_MISMATCH:{capability_id}")
        return result
