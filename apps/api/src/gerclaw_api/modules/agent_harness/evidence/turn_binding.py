"""Terminal assembly of citations and their per-claim bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.evidence.contracts import ClaimEvidenceAudit
from gerclaw_api.modules.agent_harness.evidence.markers import (
    audit_claim_evidence,
    bind_citation_markers,
    validate_public_citation_markers,
)
from gerclaw_api.modules.contracts import Citation


@dataclass(frozen=True, slots=True)
class BoundTurnEvidence:
    """Normalized answer text, admitted citations, and claim audit."""

    text: str
    citations: tuple[Citation, ...]
    claim_audit: ClaimEvidenceAudit


def bind_turn_evidence(
    text: str,
    *,
    initial_local: list[Citation],
    additional_local: list[Citation],
    web: list[Citation],
    attachments: list[Citation],
    is_clinical_claim: Callable[[str], bool],
    markers_already_bound: bool = False,
) -> BoundTurnEvidence:
    """Deduplicate sources, bind E/W markers, then audit every claim segment."""

    initial_source_ids = {item.source_id for item in initial_local}
    additional = [item for item in additional_local if item.source_id not in initial_source_ids]
    citations = [*initial_local, *web, *additional, *attachments]
    normalized_text = (
        validate_public_citation_markers(text, citation_count=len(citations))
        if markers_already_bound
        else bind_citation_markers(
            text,
            local_citation_count=len(initial_local),
            web_citation_count=len(web),
            web_citation_offset=len(initial_local),
        )
    )
    return BoundTurnEvidence(
        text=normalized_text,
        citations=tuple(citations),
        claim_audit=audit_claim_evidence(
            normalized_text,
            citations=citations,
            is_clinical_claim=is_clinical_claim,
        ),
    )
