"""Terminal assembly of citations and their per-claim bindings."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.evidence.contracts import ClaimEvidenceAudit
from gerclaw_api.modules.agent_harness.evidence.markers import (
    audit_claim_evidence,
    bind_citation_markers,
    validate_public_citation_markers,
)
from gerclaw_api.modules.agent_harness.protocols import AgentContext
from gerclaw_api.modules.contracts import Citation

_REFERENTIAL_FOLLOW_UP = re.compile(
    r"基于(?:刚才|之前|上述|上面)|(?:刚才|之前|上述|上面|这个情况|这些情况)"
)
_MAX_EVIDENCE_QUERY_CHARACTERS = 4_000


@dataclass(frozen=True, slots=True)
class BoundTurnEvidence:
    """Normalized answer text, admitted citations, and claim audit."""

    text: str
    citations: tuple[Citation, ...]
    claim_audit: ClaimEvidenceAudit


def resolve_referential_evidence_query(
    user_message: str,
    context: AgentContext,
    *,
    is_medical_message: Callable[[str], bool],
) -> str:
    """Make a bounded follow-up query self-contained for retrieval only."""

    if _REFERENTIAL_FOLLOW_UP.search(user_message) is None:
        return user_message
    previous = next(
        (
            item.text
            for item in reversed(context.conversation_history)
            if item.role == "user" and is_medical_message(item.text)
        ),
        "",
    )
    if not previous:
        return user_message
    current_budget = min(len(user_message), _MAX_EVIDENCE_QUERY_CHARACTERS)
    previous_budget = max(0, _MAX_EVIDENCE_QUERY_CHARACTERS - current_budget - 1)
    if previous_budget == 0:
        return user_message[:_MAX_EVIDENCE_QUERY_CHARACTERS]
    return f"{previous[-previous_budget:]}\n{user_message[:current_budget]}"


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
