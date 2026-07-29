"""Agent Harness public surface."""

from gerclaw_api.modules.agent_harness.components import HarnessComponents
from gerclaw_api.modules.agent_harness.config import ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.harness import ProductionAgentHarness
from gerclaw_api.modules.agent_harness.protocols import (
    AgentContext,
    AgentHarness,
    ConversationHistoryMessage,
    StreamEvent,
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
    "AgentContext",
    "AgentHarness",
    "AgentHarnessError",
    "AgentIterationLimitError",
    "ConversationHistoryMessage",
    "EmptyAgentResponseError",
    "HarnessComponents",
    "ProductionAgentHarness",
    "ResolvedHarnessConfig",
    "StreamEvent",
    "UnsupportedAgentContextError",
]
