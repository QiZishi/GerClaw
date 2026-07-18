"""Stable orchestration failures that are safe to map at the API boundary."""


class ChatReplayUnavailableError(RuntimeError):
    """A terminal trace has no valid response that can be replayed."""


class ChatCancellationFinalizationError(RuntimeError):
    """A requested cancellation did not reach a durable terminal Trace."""
