"""Policy-gated external tool execution interface."""

from __future__ import annotations

from typing import Protocol

from gerclaw_api.modules.contracts import ExecutionContext, ToolInvocation, ToolResult


class ToolModule(Protocol):
    """Validate permissions and safety both before and after a tool call."""

    async def execute(self, context: ExecutionContext, invocation: ToolInvocation) -> ToolResult:
        """Execute one approved invocation and return an auditable result."""
