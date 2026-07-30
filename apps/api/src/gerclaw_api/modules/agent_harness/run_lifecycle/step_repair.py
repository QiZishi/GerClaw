"""Typed, content-free repair decisions for private answer attempts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class StepRepairDecision:
    """One bounded repair instruction selected from an explicit error type."""

    error_code: str
    field_paths: tuple[str, ...]
    contract_version: str
    checkpoint_id: str
    instruction: str
    repair_action: Literal["retry_from_pre_model_checkpoint"] = "retry_from_pre_model_checkpoint"

    @property
    def signature(self) -> tuple[str, tuple[str, ...], str, str]:
        return (
            self.error_code,
            self.field_paths,
            self.contract_version,
            self.checkpoint_id,
        )
