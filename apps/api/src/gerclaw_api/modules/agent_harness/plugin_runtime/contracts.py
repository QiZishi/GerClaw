"""Manifest and Protocol for governed, reusable clinical capabilities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from agentscope.tool import ToolBase
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime.models import RuntimePrincipal, ToolCapability
from gerclaw_api.security import JsonValue


class PluginRuntimeError(RuntimeError):
    """Stable capability selection or invocation failure."""


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    version: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    risk_level: Literal["low", "medium", "high"]
    automatic_selection: bool = False
    required_tools: tuple[str, ...] = Field(default=(), max_length=50)
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)
    output_schema: dict[str, JsonValue] = Field(default_factory=dict)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    result_ref: str = Field(min_length=1, max_length=256)
    public_summary: str = Field(min_length=1, max_length=500)
    reused: bool = False


class PluginRuntime(Protocol):
    def manifests(self) -> tuple[PluginManifest, ...]:
        """Return the governed capability allowlist."""

    async def invoke(
        self, capability_id: str, payload: dict[str, JsonValue]
    ) -> CapabilityResult:
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
    ) -> Sequence[ToolBase]:
        """Build permission-enforcing AgentScope tool proxies."""


class ToolRegistryFactory(Protocol):
    def __call__(self) -> ToolRegistryPort:
        """Create one request-scoped registry."""
