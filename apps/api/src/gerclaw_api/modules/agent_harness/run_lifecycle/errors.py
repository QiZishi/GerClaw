"""Stable, typed failures exposed by the Agent Harness facade."""


class AgentHarnessError(RuntimeError):
    """Base class for safe Agent Harness failures."""


class UnsupportedAgentContextError(AgentHarnessError):
    """Raised when a future module reference has not been validated yet."""


class AgentIterationLimitError(AgentHarnessError):
    """Raised when AgentScope cannot finish within the bounded ReAct loop."""


class AgentApprovalRequiredError(AgentHarnessError):
    """Raised after requested side effects have been durably parked for HITL."""

    def __init__(self, message: str, *, approval_ids: tuple[str, ...] = ()) -> None:
        self.approval_ids = approval_ids
        super().__init__(message)


class EmptyAgentResponseError(AgentHarnessError):
    """Raised when a model finishes without public text."""


class AgentOutputProtocolError(AgentHarnessError):
    """Raised when provider/tool protocol markup escaped into answer text."""
