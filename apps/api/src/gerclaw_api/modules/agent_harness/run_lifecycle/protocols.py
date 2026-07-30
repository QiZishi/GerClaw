"""Dependency-injection boundary for lifecycle primitives."""

from collections.abc import Callable
from typing import Protocol

from gerclaw_api.modules.agent_harness.run_lifecycle.streaming import (
    CanonicalTextStream,
    SafeSentenceBuffer,
)


class RunLifecycle(Protocol):
    def canonical_stream(self) -> CanonicalTextStream:
        """Create an isolated canonical stream for one run."""

    def sentence_buffer(
        self,
        evidence_available: Callable[[str], bool],
    ) -> SafeSentenceBuffer:
        """Create an isolated medical sentence guard for one run."""


class ProductionRunLifecycle:
    """Stateless production factory for public stream guards."""

    def canonical_stream(self) -> CanonicalTextStream:
        return CanonicalTextStream()

    def sentence_buffer(
        self,
        evidence_available: Callable[[str], bool],
    ) -> SafeSentenceBuffer:
        return SafeSentenceBuffer(evidence_available)
