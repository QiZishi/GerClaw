"""Provider-neutral admission policy for traceable local medical evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.evidence.contracts import (
    EvidenceAdmissionError,
    EvidenceRecord,
)
from gerclaw_api.modules.contracts import Citation
from gerclaw_api.modules.rag.protocols import RetrievalResult
from gerclaw_api.modules.validation import (
    RAGEvidenceContractValidationError,
    validate_local_rag_evidence_provenance,
)

_SOURCE_AUTHORITY = {
    "guideline": 4,
    "consensus": 3,
    "textbook": 2,
    "literature": 1,
}
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AdmittedLocalEvidence:
    """One admitted record plus non-public fields used for deterministic ranking."""

    record: EvidenceRecord
    source_category: str
    relevance_score: float

    def to_citation(self) -> Citation:
        """Project the exact adopted text without inventing missing metadata."""

        if (
            self.record.locator is None
            or self.record.adopted_text is None
            or self.record.status == "unavailable"
        ):
            raise EvidenceAdmissionError("unavailable evidence cannot become a citation")
        return Citation(
            source_id=self.record.evidence_id,
            title=self.record.title,
            locator=self.record.locator,
            excerpt=self.record.adopted_text,
            score=self.relevance_score,
            corpus="local_knowledge_base",
        )


class EvidenceAdmissionPolicy:
    """Apply absolute relevance, source authority, and duplicate gates."""

    def __init__(self, *, minimum_score: float, limit: int) -> None:
        if not 0 <= minimum_score <= 1:
            raise ValueError("minimum_score must be between 0 and 1")
        if not 1 <= limit <= 50:
            raise ValueError("evidence limit must be between 1 and 50")
        self._minimum_score = minimum_score
        self._limit = limit

    def admit(self, record: EvidenceRecord) -> EvidenceRecord:
        """Reject unusable records at the final citation admission boundary."""

        if (
            record.status == "unavailable"
            or record.locator is None
            or record.adopted_text is None
        ):
            raise EvidenceAdmissionError("evidence is unavailable")
        return record

    def admit_local_results(
        self,
        results: list[RetrievalResult],
    ) -> list[AdmittedLocalEvidence]:
        """Normalize, rank, and deduplicate validated local RAG results."""

        candidates: list[AdmittedLocalEvidence] = []
        for result in results:
            if result.score < self._minimum_score:
                continue
            try:
                provenance = validate_local_rag_evidence_provenance(result.metadata)
            except RAGEvidenceContractValidationError:
                continue
            adopted_text = result.content[:2_000].strip()
            if not adopted_text:
                continue
            locator = (
                f"{result.source} | {provenance.chapter} | chunk "
                f"{provenance.chunk_index + 1}/{provenance.total_chunks}"
            )
            record = self.admit(
                EvidenceRecord(
                    evidence_id=provenance.chunk_id,
                    source_type="knowledge_base",
                    title=provenance.title,
                    year=provenance.publish_year,
                    status="verified",
                    locator=locator,
                    adopted_text=adopted_text,
                    applicability=(
                        "经本轮检索判定与当前请求相关, "
                        "仍需结合患者个体情况和专业人员复核。"
                    ),
                )
            )
            candidates.append(
                AdmittedLocalEvidence(
                    record=record,
                    source_category=provenance.source_type,
                    relevance_score=result.score,
                )
            )

        candidates.sort(
            key=lambda item: (
                -_SOURCE_AUTHORITY[item.source_category],
                -item.relevance_score,
                -(item.record.year or 0),
                item.record.evidence_id,
            )
        )
        admitted: list[AdmittedLocalEvidence] = []
        seen_ids: set[str] = set()
        seen_text: set[str] = set()
        for candidate in candidates:
            normalized_text = _WHITESPACE.sub(
                " ", candidate.record.adopted_text or ""
            ).strip().casefold()
            text_fingerprint = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
            if (
                candidate.record.evidence_id in seen_ids
                or text_fingerprint in seen_text
            ):
                continue
            admitted.append(candidate)
            seen_ids.add(candidate.record.evidence_id)
            seen_text.add(text_fingerprint)
            if len(admitted) >= self._limit:
                break
        return admitted

    def citations_from_local_results(
        self,
        results: list[RetrievalResult],
    ) -> list[Citation]:
        """Return only citations whose adopted text passed every admission gate."""

        return [item.to_citation() for item in self.admit_local_results(results)]
