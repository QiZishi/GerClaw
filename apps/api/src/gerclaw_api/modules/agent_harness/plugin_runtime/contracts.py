"""Manifest and Protocol for governed, reusable clinical capabilities."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum
from typing import Any, Literal, Protocol, cast

from agentscope.tool import ToolBase
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime.models import RuntimePrincipal, ToolCapability
from gerclaw_api.security import JsonValue

ToolExecutionPreflight = Callable[
    [ToolCapability, dict[str, Any]],
    Awaitable[None],
]


class PluginRuntimeError(RuntimeError):
    """Stable capability selection or invocation failure."""


class CapabilityInvocationContext(BaseModel):
    """Versioned owner scope passed to every governed capability adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(min_length=1, max_length=128)


class CapabilityEntrypoint(StrEnum):
    """Existing owner boundary that performs the capability's real work."""

    CGA_ASSESSMENT = "cga_assessment"
    MEDICATION_REVIEW_INTAKE = "medication_review_intake"
    FIVE_PRESCRIPTION_INTAKE = "five_prescription_intake"
    RUN_ARTIFACT = "run_artifact"


class CapabilitySelectionMode(StrEnum):
    """A capability may be requested explicitly or selected by code-owned rules."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"
    WORKFLOW = "workflow"


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    risk_level: Literal["low", "medium", "high"]
    owner_module: str = Field(
        default="agent_harness",
        pattern=r"^[a-z][a-z0-9_]{1,63}$",
    )
    entrypoint: CapabilityEntrypoint | None = None
    automatic_selection: bool = False
    manual_selection: bool = True
    supported_workflows: tuple[str, ...] = Field(default=("standard",), max_length=10)
    required_tools: tuple[str, ...] = Field(default=(), max_length=50)
    shared_result_kinds: tuple[str, ...] = Field(default=(), max_length=20)
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)
    output_schema: dict[str, JsonValue] = Field(default_factory=dict)


class SelectedCapability(BaseModel):
    """Content-free selection decision for one allowlisted capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    source: CapabilitySelectionMode
    entrypoint: CapabilityEntrypoint
    owner_module: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")


class CapabilitySelection(BaseModel):
    """Bounded multi-capability selection; it never contains user content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: tuple[SelectedCapability, ...] = Field(default=(), max_length=20)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.capability_id for item in self.selected)


class CapabilityCatalogRead(BaseModel):
    """Public allowlist; owner entrypoints remain server-controlled."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capabilities: tuple[PluginManifest, ...] = Field(default=(), max_length=50)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    result_ref: str = Field(min_length=1, max_length=256)
    public_summary: str = Field(min_length=1, max_length=500)
    reused: bool = False


def capability_contract_schemas() -> tuple[
    dict[str, JsonValue],
    dict[str, JsonValue],
]:
    """Return the exact schemas enforced by the current owner adapter boundary."""

    return (
        cast(dict[str, JsonValue], CapabilityInvocationContext.model_json_schema()),
        cast(dict[str, JsonValue], CapabilityResult.model_json_schema()),
    )


class PluginRuntime(Protocol):
    def manifests(self) -> tuple[PluginManifest, ...]:
        """Return the governed capability allowlist."""

    async def invoke(self, capability_id: str, payload: dict[str, JsonValue]) -> CapabilityResult:
        """Invoke one capability through its existing owner."""


class ToolRegistryPort(Protocol):
    def register(
        self,
        tool: ToolBase,
        capability: ToolCapability,
        input_model: type[BaseModel],
    ) -> None:
        """Register one governed tool contract."""

    def capabilities(self) -> list[ToolCapability]:
        """Return registered immutable capabilities."""

    def input_models(self) -> dict[str, type[BaseModel]]:
        """Return registered input schemas."""

    def build_tools(
        self,
        *,
        principal: RuntimePrincipal,
        outbound_redacted_tools: frozenset[str],
        execution_preflight: ToolExecutionPreflight | None = None,
    ) -> Sequence[ToolBase]:
        """Build permission-enforcing AgentScope tool proxies."""


class ToolRegistryFactory(Protocol):
    def __call__(self) -> ToolRegistryPort:
        """Create one request-scoped registry."""
