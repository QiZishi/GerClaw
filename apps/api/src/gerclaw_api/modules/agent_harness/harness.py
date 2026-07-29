"""Compatibility facade for the modular production Agent Harness."""

from gerclaw_api.modules.agent_harness.run_lifecycle import (
    AgentApprovalRequiredError,
    AgentHarnessError,
    AgentIterationLimitError,
    EmptyAgentResponseError,
    UnsupportedAgentContextError,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.production import (
    ProductionAgentHarness,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.production import (
    _CanonicalTextStream as _CanonicalTextStream,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.production import (
    _final_agent_text as _final_agent_text,
)

__all__ = [
    "AgentApprovalRequiredError",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "EmptyAgentResponseError",
    "ProductionAgentHarness",
    "UnsupportedAgentContextError",
]
