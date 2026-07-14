"""Channel-independent input validation and output rendering interface."""

from __future__ import annotations

from typing import Literal, Protocol

from gerclaw_api.modules.contracts import AgentRequest, AgentResponse
from gerclaw_api.security import JsonValue


class InputOutputModule(Protocol):
    """Normalize multimodal input and render safety-reviewed output."""

    async def normalize(self, request: AgentRequest) -> AgentRequest:
        """Validate and normalize one already size-limited request."""

    async def render(
        self, response: AgentResponse, channel: Literal["web", "voice"]
    ) -> dict[str, JsonValue]:
        """Render one safe response for the target channel."""
