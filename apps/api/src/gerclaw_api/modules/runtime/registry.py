"""Unique governed AgentScope tool registry with strict execution boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from agentscope.permission import PermissionBehavior as AgentScopeBehavior
from agentscope.permission import PermissionContext
from agentscope.permission import PermissionDecision as AgentScopeDecision
from agentscope.tool import ToolBase, ToolChunk
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.runtime.models import (
    PermissionBehavior,
    RuntimePrincipal,
    ToolCapability,
    ToolInvocationRequest,
)
from gerclaw_api.modules.runtime.permission import RuntimePermissionEngine
from gerclaw_api.modules.security_evaluation.evaluator import (
    SecurityEvaluationError,
    SecurityProfileRegistry,
)


class ToolRegistryError(RuntimeError):
    """Base class for stable governed-tool failures."""


class ToolInputInvalidError(ToolRegistryError):
    """Input failed schema or bounded-size validation."""


class ToolOutputInvalidError(ToolRegistryError):
    """Output exceeded its declared boundary."""


class ToolExecutionTimeoutError(ToolRegistryError):
    """Tool did not finish inside its capability timeout."""


class ToolSecurityProfileError(ToolRegistryError):
    """A tool cannot be enabled without a compatible security-risk profile."""


def _json_bytes(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ToolInputInvalidError("tool payload is not canonical JSON") from error


class GovernedTool(ToolBase):
    """AgentScope ToolBase proxy that cannot bypass GerClaw authorization."""

    def __init__(
        self,
        *,
        delegate: ToolBase,
        capability: ToolCapability,
        input_model: type[BaseModel],
        engine: RuntimePermissionEngine,
        principal: RuntimePrincipal,
        outbound_data_redacted: bool,
    ) -> None:
        super().__init__()
        if delegate.name != capability.name:
            raise ValueError("delegate name does not match Runtime capability")
        self._delegate = delegate
        self._capability = capability
        self._input_model = input_model
        self._engine = engine
        self._principal = principal
        self._outbound_data_redacted = outbound_data_redacted
        self._permission_permits: dict[str, int] = {}
        self.name = delegate.name
        self.description = delegate.description
        self.input_schema = input_model.model_json_schema()
        self.is_concurrency_safe = delegate.is_concurrency_safe
        self.is_read_only = delegate.is_read_only
        self.is_external_tool = delegate.is_external_tool
        self.is_state_injected = delegate.is_state_injected
        self.is_mcp = delegate.is_mcp
        self.mcp_name = delegate.mcp_name

    def _validated_input(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        if _json_bytes(tool_input) > self._capability.max_input_bytes:
            raise ToolInputInvalidError("tool input exceeded the registered byte limit")
        try:
            validated = self._input_model.model_validate(tool_input)
        except ValidationError as error:
            raise ToolInputInvalidError("tool input failed its registered schema") from error
        return validated.model_dump(mode="python")

    @staticmethod
    def _permit_key(tool_input: dict[str, Any]) -> str:
        """Create an opaque per-input capability token without retaining input text."""

        encoded = json.dumps(
            tool_input, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> AgentScopeDecision:
        try:
            validated = self._validated_input(tool_input)
        except ToolInputInvalidError:
            return AgentScopeDecision(
                behavior=AgentScopeBehavior.DENY,
                message="工具参数未通过服务端 schema 或大小校验。",
                decision_reason="RUNTIME_INPUT_INVALID",
                bypass_immune=True,
            )
        delegate_decision = await self._delegate.check_permissions(validated, context)
        request = ToolInvocationRequest(
            invocation_id=f"invoke_{uuid.uuid4().hex}",
            tool_name=self.name,
            tool_version=self._capability.version,
            arguments=validated,
            outbound_data_redacted=self._outbound_data_redacted,
        )
        verdict = self._engine.evaluate(
            self._principal,
            request,
            agentscope_decision=delegate_decision,
        )
        behavior = {
            PermissionBehavior.ALLOW: AgentScopeBehavior.ALLOW,
            PermissionBehavior.DENY: AgentScopeBehavior.DENY,
            PermissionBehavior.ASK: AgentScopeBehavior.ASK,
        }[verdict.behavior]
        if behavior is AgentScopeBehavior.ALLOW:
            key = self._permit_key(validated)
            self._permission_permits[key] = self._permission_permits.get(key, 0) + 1
        return AgentScopeDecision(
            behavior=behavior,
            message=verdict.message,
            decision_reason=verdict.code.value,
            updated_input=validated,
            bypass_immune=verdict.bypass_immune,
        )

    async def call(self, **kwargs: Any) -> ToolChunk | AsyncGenerator[ToolChunk, None]:
        validated = self._validated_input(kwargs)
        key = self._permit_key(validated)
        permits = self._permission_permits.get(key, 0)
        if permits <= 0:
            raise ToolRegistryError("tool execution requires a fresh Runtime permission verdict")
        if permits == 1:
            self._permission_permits.pop(key)
        else:
            self._permission_permits[key] = permits - 1
        try:
            async with asyncio.timeout(self._capability.timeout_seconds):
                result = await self._delegate(**validated)
        except TimeoutError as error:
            raise ToolExecutionTimeoutError("tool execution exceeded its timeout") from error
        if isinstance(result, AsyncGenerator):
            return self._bounded_stream(result)
        self._validate_chunk(result)
        return result

    async def _bounded_stream(
        self,
        stream: AsyncGenerator[ToolChunk, None],
    ) -> AsyncGenerator[ToolChunk, None]:
        total = 0
        try:
            async with asyncio.timeout(self._capability.timeout_seconds):
                async for chunk in stream:
                    total += len(chunk.model_dump_json().encode("utf-8"))
                    if total > self._capability.max_output_bytes:
                        raise ToolOutputInvalidError(
                            "streamed tool output exceeded the registered byte limit"
                        )
                    yield chunk
        except TimeoutError as error:
            raise ToolExecutionTimeoutError("streamed tool execution timed out") from error

    def _validate_chunk(self, result: object) -> None:
        if not isinstance(result, ToolChunk):
            raise ToolOutputInvalidError("tool returned an unsupported result type")
        if len(result.model_dump_json().encode("utf-8")) > self._capability.max_output_bytes:
            raise ToolOutputInvalidError("tool output exceeded the registered byte limit")


class GovernedToolRegistry:
    """Build one request-scoped allowlisted toolkit from immutable registrations."""

    def __init__(self, *, security_profiles: SecurityProfileRegistry | None = None) -> None:
        self._registrations: dict[str, tuple[ToolBase, ToolCapability, type[BaseModel]]] = {}
        self._security_profiles = security_profiles

    def register(
        self,
        delegate: ToolBase,
        capability: ToolCapability,
        input_model: type[BaseModel],
    ) -> None:
        if delegate.name in self._registrations:
            raise ValueError(f"duplicate governed tool registration: {delegate.name}")
        if delegate.name != capability.name:
            raise ValueError("delegate and capability names differ")
        if self._security_profiles is not None:
            try:
                self._security_profiles.assess_tool(capability)
            except SecurityEvaluationError as error:
                raise ToolSecurityProfileError(str(error)) from error
        self._registrations[delegate.name] = (delegate, capability, input_model)

    def capabilities(self) -> list[ToolCapability]:
        return [item[1] for item in self._registrations.values()]

    def input_models(self) -> dict[str, type[BaseModel]]:
        """Return server-owned schemas for both execution and HITL persistence."""

        return {name: item[2] for name, item in self._registrations.items()}

    def build_tools(
        self,
        *,
        principal: RuntimePrincipal,
        outbound_redacted_tools: frozenset[str] = frozenset(),
    ) -> list[GovernedTool]:
        if self._security_profiles is not None:
            for name, (_, capability, _) in self._registrations.items():
                try:
                    self._security_profiles.assess_tool(
                        capability,
                        outbound_data_redacted=name in outbound_redacted_tools,
                    )
                except SecurityEvaluationError as error:
                    raise ToolSecurityProfileError(str(error)) from error
        engine = RuntimePermissionEngine(self.capabilities())
        return [
            GovernedTool(
                delegate=delegate,
                capability=capability,
                input_model=input_model,
                engine=engine,
                principal=principal,
                outbound_data_redacted=name in outbound_redacted_tools,
            )
            for name, (delegate, capability, input_model) in self._registrations.items()
        ]
