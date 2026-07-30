"""Traceable evidence contracts."""

from gerclaw_api.modules.agent_harness.evidence.admission import (
    AdmittedLocalEvidence,
    EvidenceAdmissionPolicy,
)
from gerclaw_api.modules.agent_harness.evidence.contracts import (
    ClaimEvidenceAudit,
    EvidenceAdmissionError,
    EvidenceClaimBinding,
    EvidenceRecord,
    EvidenceValidator,
)
from gerclaw_api.modules.agent_harness.evidence.markers import (
    CitationMarkerValidationError,
    ModelCitationBindingScope,
    audit_claim_evidence,
    bind_citation_markers,
    segment_has_admitted_model_marker,
    validate_public_citation_markers,
)
from gerclaw_api.modules.agent_harness.evidence.turn_binding import (
    BoundTurnEvidence,
    bind_turn_evidence,
)

__all__ = [
    "AdmittedLocalEvidence",
    "BoundTurnEvidence",
    "CitationMarkerValidationError",
    "ClaimEvidenceAudit",
    "EvidenceAdmissionError",
    "EvidenceAdmissionPolicy",
    "EvidenceClaimBinding",
    "EvidenceRecord",
    "EvidenceValidator",
    "ModelCitationBindingScope",
    "audit_claim_evidence",
    "bind_citation_markers",
    "bind_turn_evidence",
    "segment_has_admitted_model_marker",
    "validate_public_citation_markers",
]
