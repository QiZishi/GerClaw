"""Run lifecycle contracts and safe streaming primitives."""

from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import (
    AgentStreamResult,
    project_agent_stream,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
    AgentOutputProtocolError,
    EmptyAgentResponseError,
    UnsupportedAgentContextError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.output_repair import (
    OUTPUT_PROTOCOL_REPAIR_INSTRUCTION,
    AttemptRepairObserver,
    RepairableAgentSession,
    project_with_output_protocol_repair,
    run_with_output_protocol_repair,
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
    validate_public_answer_text,
)

__all__ = [
    "OUTPUT_PROTOCOL_REPAIR_INSTRUCTION",
    "AgentApprovalRequiredError",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "AgentOutputProtocolError",
    "AgentRunStateMachine",
    "AgentStreamResult",
    "AttemptRepairObserver",
    "CanonicalTextStream",
    "EmptyAgentResponseError",
    "ProductionRunLifecycle",
    "RepairableAgentSession",
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
    "project_with_output_protocol_repair",
    "run_with_output_protocol_repair",
    "validate_public_answer_text",
]
