"""Run lifecycle contracts and safe streaming primitives."""

from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
    EmptyAgentResponseError,
    UnsupportedAgentContextError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.protocols import RunLifecycle
from gerclaw_api.modules.agent_harness.run_lifecycle.streaming import (
    CanonicalTextStream,
    SafeSentenceBuffer,
    bounded_events,
)

__all__ = [
    "AgentApprovalRequiredError",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "CanonicalTextStream",
    "EmptyAgentResponseError",
    "RunLifecycle",
    "SafeSentenceBuffer",
    "UnsupportedAgentContextError",
    "bounded_events",
]
