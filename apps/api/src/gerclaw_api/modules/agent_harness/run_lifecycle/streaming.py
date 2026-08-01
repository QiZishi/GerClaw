"""Pure streaming guards used by the public Harness facade."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable

from gerclaw_api.modules.agent_harness.run_lifecycle.errors import (
    AgentHarnessError,
    AgentOutputProtocolError,
)
from gerclaw_api.modules.agent_harness.safety import sanitize_medical_text

_SENTENCE_END = re.compile(r"[。！？!?\n]")  # noqa: RUF001
_PRIVATE_PROTOCOL_MARKER = re.compile(
    r"(?:<\s*/?\s*(?:invoke|parameter|tool_call|function_call|final-clinical-state)\b|"
    r"<\|/?(?:tool_call|function_call)[^>]*\|>)",
    re.IGNORECASE,
)


async def bounded_events[EventT](
    events: AsyncIterator[EventT],
    *,
    wall_clock_seconds: float,
    timeout_error_factory: Callable[[], Exception] | None = None,
) -> AsyncIterator[EventT]:
    """Cancel a stalled model/tool stream at the configured Runtime boundary."""

    try:
        async with asyncio.timeout(wall_clock_seconds):
            async for event in events:
                yield event
    except TimeoutError as error:
        public_error = (
            timeout_error_factory()
            if timeout_error_factory is not None
            else AgentHarnessError("agent stream exceeded its wall-clock limit")
        )
        raise public_error from error


def validate_public_answer_text(value: str) -> None:
    """Reject provider/tool control syntax before staged text becomes public."""

    if _PRIVATE_PROTOCOL_MARKER.search(value):
        raise AgentOutputProtocolError(
            "provider tool protocol markup cannot enter public answer text"
        )


class SafeSentenceBuffer:
    """Hold partial sentences so unsupported certainty cannot cross SSE chunks."""

    def __init__(self) -> None:
        self._pending = ""
        self.deterministic_diagnosis_blocked = False

    def feed(self, delta: str) -> list[str]:
        self._pending += delta
        output: list[str] = []
        while match := _SENTENCE_END.search(self._pending):
            end = match.end()
            raw_sentence = self._pending[:end]
            safe_sentence = sanitize_medical_text(raw_sentence)
            self.deterministic_diagnosis_blocked |= safe_sentence != raw_sentence
            output.append(safe_sentence)
            self._pending = self._pending[end:]
        return output

    def finish(self) -> str:
        tail = sanitize_medical_text(self._pending)
        self.deterministic_diagnosis_blocked |= tail != self._pending
        self._pending = ""
        return tail


class CanonicalTextStream:
    """Strip only outer whitespace without buffering the whole model reply."""

    def __init__(self) -> None:
        self._started = False
        self._pending_whitespace = ""

    def feed(self, value: str) -> str:
        if not value:
            return ""
        candidate = self._pending_whitespace + value if self._started else value.lstrip()
        body = candidate.rstrip()
        self._pending_whitespace = candidate[len(body) :] if self._started or body else ""
        if body:
            self._started = True
        return body

    @property
    def pending_whitespace(self) -> str:
        """Whitespace accepted from deltas but not yet safe to publish."""

        return self._pending_whitespace

    def finish(self) -> None:
        """Discard terminal whitespace after the authoritative final state is known."""

        self._pending_whitespace = ""
