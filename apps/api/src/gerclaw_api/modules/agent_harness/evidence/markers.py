"""Bind model citation markers to the exact admitted terminal citation list."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.evidence.contracts import (
    ClaimEvidenceAudit,
    EvidenceClaimBinding,
)
from gerclaw_api.modules.contracts import Citation

_MODEL_MARKER = re.compile(
    r"\[\s*(?P<prefix>[EWAC])\s*(?P<index>\d{1,4})\s*\]",
    re.IGNORECASE,
)
_PUBLIC_MARKER = re.compile(r"\[C(?P<index>\d+)\]", re.IGNORECASE)
_CLAIM_SEGMENT = re.compile(r"[^。！？!?\n]+(?:[。！？!?]+|\n+|$)")  # noqa: RUF001
_WHITESPACE = re.compile(r"\s+")
_ORPHAN_MARKER_GAP = re.compile(r"[ \t]+(?=[,，。！？!?;；:：])")  # noqa: RUF001
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


class CitationMarkerValidationError(RuntimeError):
    """Raised when model text refers to evidence the server did not admit."""


@dataclass(frozen=True, slots=True)
class ModelCitationBindingScope:
    """Stable per-turn mapping from private model markers to public citations."""

    local_citation_count: int
    web_citation_count_provider: Callable[[], int]
    attachment_citation_count: int = 0

    def __post_init__(self) -> None:
        if min(self.local_citation_count, self.attachment_citation_count) < 0:
            raise ValueError("citation counts cannot be negative")

    def segment_has_evidence(self, segment: str) -> bool:
        """Check only evidence admitted for this exact model-output segment."""

        return segment_has_admitted_model_marker(
            segment,
            local_citation_count=self.local_citation_count,
            web_citation_count=self.web_citation_count_provider(),
            attachment_citation_count=self.attachment_citation_count,
        )

    def normalize_public_text(self, text: str) -> str:
        """Normalize admitted E/W markers before any text becomes public."""

        return bind_citation_markers(
            text,
            local_citation_count=self.local_citation_count,
            web_citation_count=self.web_citation_count_provider(),
            web_citation_offset=self.local_citation_count,
            attachment_citation_count=self.attachment_citation_count,
            attachment_citation_offset=(
                self.local_citation_count + self.web_citation_count_provider()
            ),
        )


def bind_citation_markers(
    text: str,
    *,
    local_citation_count: int,
    web_citation_count: int,
    web_citation_offset: int,
    attachment_citation_count: int = 0,
    attachment_citation_offset: int = 0,
) -> str:
    """Bind admitted markers and silently remove markers without a real source."""

    if (
        min(
            local_citation_count,
            web_citation_count,
            web_citation_offset,
            attachment_citation_count,
            attachment_citation_offset,
        )
        < 0
    ):
        raise ValueError("citation counts and offsets cannot be negative")

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix").upper()
        index = int(match.group("index"))
        if prefix == "C":
            return ""
        if prefix == "E":
            if not 1 <= index <= local_citation_count:
                return ""
            public_index = index
        elif prefix == "W":
            if not 1 <= index <= web_citation_count:
                return ""
            public_index = web_citation_offset + index
        else:
            if not 1 <= index <= attachment_citation_count:
                return ""
            public_index = attachment_citation_offset + index
        return f"[C{public_index}]"

    return _ORPHAN_MARKER_GAP.sub("", _MODEL_MARKER.sub(replace, text))


def segment_has_admitted_model_marker(
    segment: str,
    *,
    local_citation_count: int,
    web_citation_count: int,
    attachment_citation_count: int = 0,
) -> bool:
    """Return true only for an in-range E/W marker in this exact segment."""

    if min(local_citation_count, web_citation_count, attachment_citation_count) < 0:
        raise ValueError("citation counts cannot be negative")
    for match in _MODEL_MARKER.finditer(segment):
        prefix = match.group("prefix").upper()
        index = int(match.group("index"))
        if prefix == "E" and 1 <= index <= local_citation_count:
            return True
        if prefix == "W" and 1 <= index <= web_citation_count:
            return True
        if prefix == "A" and 1 <= index <= attachment_citation_count:
            return True
    return False


def validate_public_citation_markers(text: str, *, citation_count: int) -> str:
    """Validate server-normalized C markers and reject leaked model E/W markers."""

    if citation_count < 0:
        raise ValueError("citation count cannot be negative")
    for match in _MODEL_MARKER.finditer(text):
        if match.group("prefix").upper() != "C":
            raise CitationMarkerValidationError("model citation marker was not normalized")
        if not 1 <= int(match.group("index")) <= citation_count:
            raise CitationMarkerValidationError("public citation marker is out of range")
    return text


def audit_claim_evidence(
    text: str,
    *,
    citations: list[Citation],
    is_clinical_claim: Callable[[str], bool],
) -> ClaimEvidenceAudit:
    """Bind every detected clinical segment to its exact adopted citations."""

    claims: list[EvidenceClaimBinding] = []
    for match in _CLAIM_SEGMENT.finditer(text):
        segment = match.group(0).strip()
        if not segment or not is_clinical_claim(segment):
            continue
        indices = tuple(
            dict.fromkeys(int(item.group("index")) for item in _PUBLIC_MARKER.finditer(segment))
        )
        if any(index < 1 or index > len(citations) for index in indices):
            raise CitationMarkerValidationError("public citation marker is out of range")
        adopted = tuple(citations[index - 1] for index in indices)
        normalized = _WHITESPACE.sub(" ", segment).strip()
        claim_id = "claim_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        claims.append(
            EvidenceClaimBinding(
                claim_id=claim_id,
                claim_excerpt=normalized[:1_000],
                citation_indices=indices,
                source_ids=tuple(item.source_id for item in adopted),
                locators=tuple(item.locator for item in adopted),
                adopted_text_sha256=tuple(
                    hashlib.sha256(item.excerpt.encode("utf-8")).hexdigest() for item in adopted
                ),
                status="bound" if indices else "unbound",
            )
        )
    bound_count = sum(item.status == "bound" for item in claims)
    return ClaimEvidenceAudit(
        claims=tuple(claims),
        clinical_claim_count=len(claims),
        bound_claim_count=bound_count,
        all_clinical_claims_bound=bool(claims) and bound_count == len(claims),
    )


def prune_unbound_clinical_claims(
    text: str,
    *,
    citations: list[Citation],
    is_clinical_claim: Callable[[str], bool],
) -> tuple[str, int]:
    """Remove only clinical segments that still lack an admitted citation.

    This is the final deterministic degradation after one private model repair.
    Every non-clinical segment and every in-segment evidence binding is preserved,
    so one unsupported sentence cannot discard an otherwise useful answer.
    """

    validate_public_citation_markers(text, citation_count=len(citations))
    retained: list[str] = []
    removed_count = 0
    for match in _CLAIM_SEGMENT.finditer(text):
        segment = match.group(0)
        if is_clinical_claim(segment) and _PUBLIC_MARKER.search(segment) is None:
            removed_count += 1
            continue
        retained.append(segment)
    normalized = _EXCESS_BLANK_LINES.sub("\n\n", "".join(retained)).strip()
    return normalized, removed_count
