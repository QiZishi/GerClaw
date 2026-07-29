"""Deterministic projection of one persisted user message into ClinicalState."""

from __future__ import annotations

import uuid
from datetime import datetime

from gerclaw_api.modules.agent_harness.clinical_state.contracts import (
    ClinicalFact,
    ClinicalState,
    ClinicalStateReducer,
    FactProvenance,
)


class UserMessageClinicalProjector:
    """Record explicit user text and code-owned red-flag matches without inference."""

    def __init__(
        self,
        reducer: ClinicalStateReducer,
    ) -> None:
        self._reducer = reducer

    def project(
        self,
        current: ClinicalState,
        *,
        message_id: uuid.UUID,
        message: str,
        observed_at: datetime,
        red_flag_codes: tuple[str, ...],
    ) -> ClinicalState:
        source_id = f"message:{message_id}"
        provenance = (
            FactProvenance(
                source_type="user",
                source_id=source_id,
                observed_at=observed_at,
            ),
        )
        message_fact_id = f"user_message:{message_id}"
        observations: list[ClinicalFact] = []
        if not any(fact.fact_id == message_fact_id for fact in current.facts):
            observations.append(
                ClinicalFact(
                    fact_id=message_fact_id,
                    category="chief_complaint",
                    value=message,
                    status="reported",
                    provenance=provenance,
                )
            )
        for code in red_flag_codes:
            fact_id = f"red_flag:{code}"
            existing = next(
                (
                    fact
                    for fact in current.facts
                    if fact.fact_id == fact_id
                    and fact.category == "red_flag"
                    and fact.value == code
                ),
                None,
            )
            if existing is None:
                observations.append(
                    ClinicalFact(
                        fact_id=fact_id,
                        category="red_flag",
                        value=code,
                        status="reported",
                        provenance=provenance,
                    )
                )
        return self._reducer.reduce(current, tuple(observations))
