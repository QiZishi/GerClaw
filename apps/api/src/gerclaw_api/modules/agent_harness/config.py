"""Single resolved configuration boundary for Agent Harness components."""

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.config import Settings


class ResolvedHarnessConfig(BaseModel):
    """Validated settings consumed by the Harness after application resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_react_iterations: int = Field(ge=1, le=50)
    max_output_characters: int = Field(ge=1, le=524_288)
    max_output_bytes: int = Field(ge=4, le=16_777_216)
    evidence_top_k: int = Field(ge=1, le=100)
    memory_top_k: int = Field(ge=1, le=100)
    memory_min_score: float = Field(ge=0, le=1)
    approval_ttl_seconds: int = Field(ge=60, le=86_400)
    context_trigger_ratio: float = Field(gt=0, lt=1)
    context_reserve_ratio: float = Field(gt=0, lt=1)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ResolvedHarnessConfig":
        """Resolve application-owned settings once at the composition boundary."""

        return cls(
            max_react_iterations=settings.agent_max_react_iterations,
            max_output_characters=settings.agent_max_output_characters,
            max_output_bytes=min(settings.agent_max_output_characters * 4, 2_097_152),
            evidence_top_k=settings.agent_evidence_top_k,
            memory_top_k=settings.memory_retrieval_top_k,
            memory_min_score=settings.memory_min_score,
            approval_ttl_seconds=900,
            context_trigger_ratio=0.85,
            context_reserve_ratio=0.2,
        )
