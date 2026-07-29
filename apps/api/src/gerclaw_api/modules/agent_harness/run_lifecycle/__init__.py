"""Run lifecycle contracts and safe streaming primitives."""

from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import (
    AgentStreamResult,
    project_agent_stream,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
    EmptyAgentResponseError,
    UnsupportedAgentContextError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.protocols import (
    ProductionRunLifecycle,
    RunLifecycle,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.streaming import (
    CanonicalTextStream,
    SafeSentenceBuffer,
    bounded_events,
)

__all__ = [
    "AgentApprovalRequiredError",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "AgentStreamResult",
    "CanonicalTextStream",
    "EmptyAgentResponseError",
    "ProductionRunLifecycle",
    "RunLifecycle",
    "SafeSentenceBuffer",
    "UnsupportedAgentContextError",
    "bounded_events",
    "project_agent_stream",
]
