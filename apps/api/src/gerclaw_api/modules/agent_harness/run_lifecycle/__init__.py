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
from gerclaw_api.modules.agent_harness.run_lifecycle.state_machine import (
    AgentRunStateMachine,
    RunFenceConflictError,
    RunLifecycleState,
    RunRevisionConflictError,
    RunTerminalConflictError,
    RunTransitionError,
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
    "AgentRunStateMachine",
    "AgentStreamResult",
    "CanonicalTextStream",
    "EmptyAgentResponseError",
    "ProductionRunLifecycle",
    "RunFenceConflictError",
    "RunLifecycle",
    "RunLifecycleState",
    "RunRevisionConflictError",
    "RunTerminalConflictError",
    "RunTransitionError",
    "SafeSentenceBuffer",
    "UnsupportedAgentContextError",
    "bounded_events",
    "project_agent_stream",
]
