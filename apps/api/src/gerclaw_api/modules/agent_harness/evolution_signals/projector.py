"""Pure one-way projection from decontented Run metadata to an export signal."""

from __future__ import annotations

import hashlib
import hmac

from gerclaw_api.modules.agent_harness.evolution_signals.contracts import (
    EvolutionSignal,
    EvolutionSignalError,
    EvolutionSignalSource,
)

_RISK_BY_ROUTE = {
    "quick": "low",
    "standard": "medium",
    "deep": "high",
    "emergency": "critical",
}


class EvolutionSignalProjector:
    """Bind a Run to a non-reversible pseudonym under a purpose-specific key."""

    def __init__(self, hmac_key: bytes) -> None:
        if len(hmac_key) < 32:
            raise EvolutionSignalError("EVOLUTION_SIGNAL_HMAC_KEY_TOO_SHORT")
        self._hmac_key = hmac_key

    def project(self, source: EvolutionSignalSource) -> EvolutionSignal:
        fingerprint = self._digest(
            b"run:",
            source.run_id.bytes,
        )
        skill_ids = tuple(
            f"skill_{self._digest(b'skill:', item.encode('utf-8'))}"
            for item in source.skill_ids
        )
        return EvolutionSignal(
            run_fingerprint=fingerprint,
            route=source.route,
            run_status=source.run_status,
            error_code=source.error_code,
            risk_level=_RISK_BY_ROUTE[source.route],
            capability_ids=source.capability_ids,
            skill_ids=skill_ids,
            input_tokens=source.input_tokens,
            output_tokens=source.output_tokens,
            duration_ms=source.duration_ms,
            feedback_value=source.feedback_value,
            feedback_revision=source.feedback_revision,
            occurred_at=source.occurred_at,
        )

    def _digest(self, purpose: bytes, value: bytes) -> str:
        return hmac.new(
            self._hmac_key,
            b"gerclaw:evolution-signal:v1:" + purpose + value,
            hashlib.sha256,
        ).hexdigest()
