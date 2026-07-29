"""Compatibility facade for the modular production Agent Harness."""

from gerclaw_api.modules.agent_harness.orchestrator import (
    ProductionAgentHarness,
)
from gerclaw_api.modules.agent_harness.orchestrator import (
    _CanonicalTextStream as _CanonicalTextStream,
)
from gerclaw_api.modules.agent_harness.orchestrator import (
    _final_agent_text as _final_agent_text,
)
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
    EmptyAgentResponseError,
    UnsupportedAgentContextError,
)

__all__ = [
    "AgentApprovalRequiredError",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "EmptyAgentResponseError",
    "ProductionAgentHarness",
    "UnsupportedAgentContextError",
]
