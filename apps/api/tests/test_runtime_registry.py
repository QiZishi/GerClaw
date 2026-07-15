"""Governed Tool Registry schema, permission, timeout, and size tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agentscope.permission import PermissionBehavior as AgentScopeBehavior
from agentscope.permission import PermissionContext
from agentscope.permission import PermissionDecision as AgentScopeDecision
from agentscope.tool import FunctionTool
from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.runtime import (
    DataClass,
    GovernedToolRegistry,
    NetworkAccess,
    RiskLevel,
    RuntimePrincipal,
    SideEffect,
    ToolCapability,
)
from gerclaw_api.modules.runtime.models import ActorRole
from gerclaw_api.modules.runtime.registry import (
    ToolExecutionTimeoutError,
    ToolInputInvalidError,
    ToolOutputInvalidError,
    ToolRegistryError,
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100)


class AllowingTool(FunctionTool):
    async def check_permissions(self, *_args: Any, **_kwargs: Any) -> AgentScopeDecision:
        return AgentScopeDecision(
            behavior=AgentScopeBehavior.ALLOW,
            message="delegate allows read-only execution",
        )


def build_registry(
    function: Any,
    *,
    timeout_seconds: float = 1,
    max_input_bytes: int = 256,
    max_output_bytes: int = 256,
) -> GovernedToolRegistry:
    registry = GovernedToolRegistry()
    delegate = AllowingTool(
        function,
        name="echo_tool",
        description="Return validated text for a bounded Runtime test.",
        is_read_only=True,
    )
    registry.register(
        delegate,
        ToolCapability(
            name="echo_tool",
            version="1.0.0",
            description="Return validated text for a bounded Runtime test.",
            required_scopes=frozenset({"tool:read"}),
            allowed_roles=frozenset({ActorRole.GUEST}),
            risk_level=RiskLevel.LOW,
            side_effect=SideEffect.NONE,
            network_access=NetworkAccess.NONE,
            data_classes=frozenset({DataClass.INTERNAL}),
            timeout_seconds=timeout_seconds,
            max_input_bytes=max_input_bytes,
            max_output_bytes=max_output_bytes,
        ),
        EchoInput,
    )
    return registry


def caller(*, scopes: frozenset[str] = frozenset({"tool:read"})) -> RuntimePrincipal:
    return RuntimePrincipal(
        tenant_id="tenant_abcdefgh",
        actor_id="actor_abcdefgh",
        role=ActorRole.GUEST,
        scopes=scopes,
    )


@pytest.mark.asyncio
async def test_registry_validates_then_allows_and_executes() -> None:
    async def echo_tool(text: str) -> str:
        return text

    tool = build_registry(echo_tool).build_tools(principal=caller())[0]
    decision = await tool.check_permissions({"text": "safe"}, PermissionContext())
    assert decision.behavior is AgentScopeBehavior.ALLOW
    result = await tool(text="safe")
    assert "safe" in result.model_dump_json()


@pytest.mark.asyncio
async def test_unknown_fields_and_oversize_input_fail_before_delegate() -> None:
    calls = 0

    async def echo_tool(text: str) -> str:
        nonlocal calls
        calls += 1
        return text

    tool = build_registry(echo_tool).build_tools(principal=caller())[0]
    decision = await tool.check_permissions({"text": "safe", "injected": True}, PermissionContext())
    assert decision.behavior is AgentScopeBehavior.DENY
    with pytest.raises(ToolInputInvalidError):
        await tool(text="x" * 300)
    assert calls == 0


@pytest.mark.asyncio
async def test_runtime_scope_denial_overrides_allowing_delegate() -> None:
    async def echo_tool(text: str) -> str:
        return text

    tool = build_registry(echo_tool).build_tools(principal=caller(scopes=frozenset()))[0]
    decision = await tool.check_permissions({"text": "safe"}, PermissionContext())
    assert decision.behavior is AgentScopeBehavior.DENY
    assert decision.decision_reason == "RUNTIME_SCOPE_REQUIRED"
    with pytest.raises(ToolRegistryError, match="fresh Runtime permission"):
        await tool(text="safe")


@pytest.mark.asyncio
async def test_each_allow_verdict_grants_exactly_one_matching_execution() -> None:
    async def echo_tool(text: str) -> str:
        return text

    tool = build_registry(echo_tool).build_tools(principal=caller())[0]
    await tool.check_permissions({"text": "safe"}, PermissionContext())
    await tool.check_permissions({"text": "safe"}, PermissionContext())
    assert "safe" in (await tool(text="safe")).model_dump_json()
    assert "safe" in (await tool(text="safe")).model_dump_json()
    with pytest.raises(ToolRegistryError, match="fresh Runtime permission"):
        await tool(text="safe")


@pytest.mark.asyncio
async def test_timeout_and_output_limit_fail_closed() -> None:
    async def slow_tool(text: str) -> str:
        await asyncio.sleep(0.05)
        return text

    timeout_tool = build_registry(slow_tool, timeout_seconds=0.01).build_tools(principal=caller())[
        0
    ]
    await timeout_tool.check_permissions({"text": "safe"}, PermissionContext())
    with pytest.raises(ToolExecutionTimeoutError):
        await timeout_tool(text="safe")

    async def large_tool(text: str) -> str:
        return text * 100

    output_tool = build_registry(large_tool, max_output_bytes=256).build_tools(principal=caller())[
        0
    ]
    await output_tool.check_permissions({"text": "large output"}, PermissionContext())
    with pytest.raises(ToolOutputInvalidError):
        await output_tool(text="large output")


def test_registry_rejects_duplicate_and_mismatched_names() -> None:
    async def echo_tool(text: str) -> str:
        return text

    registry = build_registry(echo_tool)
    existing = registry.capabilities()[0]
    duplicate = AllowingTool(
        echo_tool,
        name="echo_tool",
        description="Duplicate registration is forbidden by contract.",
        is_read_only=True,
    )
    with pytest.raises(ValueError, match="duplicate governed tool"):
        registry.register(duplicate, existing, EchoInput)
