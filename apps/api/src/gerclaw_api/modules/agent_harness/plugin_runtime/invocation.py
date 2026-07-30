"""Validated dispatch from governed manifests to injected owner entrypoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from pydantic import ValidationError

from gerclaw_api.modules.agent_harness.plugin_runtime.catalog import (
    GovernedCapabilityCatalog,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import (
    CapabilityEntrypoint,
    CapabilityInvocationContext,
    CapabilityResult,
    PluginManifest,
    PluginRuntimeError,
    capability_contract_schemas,
)
from gerclaw_api.security import JsonValue

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
        for manifest in self._catalog.manifests():
            self._require_supported_schema(manifest.capability_id)

    def manifests(self) -> tuple[PluginManifest, ...]:
        return self._catalog.manifests()

    async def invoke(
        self,
        capability_id: str,
        payload: dict[str, JsonValue],
    ) -> CapabilityResult:
        manifest = self._catalog.resolve(capability_id)
        self._require_supported_schema(capability_id)
        if manifest.entrypoint is None:  # pragma: no cover - catalog invariant
            raise PluginRuntimeError(f"CAPABILITY_ENTRYPOINT_MISSING:{capability_id}")
        handler = self._handlers.get(manifest.entrypoint)
        if handler is None:
            raise PluginRuntimeError(f"CAPABILITY_OWNER_UNAVAILABLE:{capability_id}")
        try:
            context = CapabilityInvocationContext.model_validate(payload)
        except ValidationError as error:
            raise PluginRuntimeError(f"CAPABILITY_INPUT_INVALID:{capability_id}") from error
        raw_result = await handler(context, capability_id)
        try:
            result = CapabilityResult.model_validate(raw_result)
        except ValidationError as error:
            raise PluginRuntimeError(f"CAPABILITY_OUTPUT_INVALID:{capability_id}") from error
        if result.capability_id != capability_id:
            raise PluginRuntimeError(f"CAPABILITY_OWNER_RESULT_MISMATCH:{capability_id}")
        return result

    def _require_supported_schema(self, capability_id: str) -> None:
        manifest = self._catalog.resolve(capability_id)
        input_schema, output_schema = capability_contract_schemas()
        if manifest.input_schema != input_schema or manifest.output_schema != output_schema:
            raise PluginRuntimeError(f"CAPABILITY_SCHEMA_UNSUPPORTED:{manifest.capability_id}")
