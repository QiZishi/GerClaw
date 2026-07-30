"""Shared dual-threshold model context capacity contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextWindowLimits:
    """Resolved soft target and hard input ceiling for one model window."""

    soft_trigger_tokens: int
    hard_stop_input_tokens: int
    target_tokens: int
    output_reserve_tokens: int

    @classmethod
    def resolve(
        cls,
        *,
        model_context_tokens: int,
        trigger_ratio: float,
        hard_stop_ratio: float,
        reserve_ratio: float,
        output_reserve_tokens: int,
    ) -> ContextWindowLimits:
        if model_context_tokens <= 0:
            raise ValueError("model context size must be positive")
        if not 0 < reserve_ratio < trigger_ratio < hard_stop_ratio < 1:
            raise ValueError(
                "context ratios must satisfy 0 < reserve < soft trigger < hard stop < 1"
            )
        if output_reserve_tokens < 0:
            raise ValueError("output reserve cannot be negative")
        hard_stop_input_tokens = min(
            model_context_tokens - output_reserve_tokens,
            int(model_context_tokens * hard_stop_ratio),
        )
        soft_trigger_tokens = min(
            int(model_context_tokens * trigger_ratio),
            hard_stop_input_tokens - 1,
        )
        target_tokens = min(
            soft_trigger_tokens,
            int(model_context_tokens * (trigger_ratio - reserve_ratio)),
        )
        if soft_trigger_tokens <= 0 or hard_stop_input_tokens <= 1 or target_tokens <= 0:
            raise ValueError("output reserve exceeds usable model context")
        return cls(
            soft_trigger_tokens=soft_trigger_tokens,
            hard_stop_input_tokens=hard_stop_input_tokens,
            target_tokens=target_tokens,
            output_reserve_tokens=output_reserve_tokens,
        )
