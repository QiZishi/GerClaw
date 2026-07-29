"""Deterministic, provenance-preserving ClinicalState reduction."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from gerclaw_api.modules.agent_harness.clinical_state.contracts import (
    BoundedClinicalText,
    ClinicalFact,
    ClinicalState,
    ClinicalStateError,
    FactProvenance,
)


def _deduplicate[T](values: Iterable[T]) -> tuple[T, ...]:
    """Preserve first-seen order without requiring values to be hashable."""

    unique: list[T] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return tuple(unique)


def _merge_provenance(
    current: tuple[FactProvenance, ...],
    incoming: tuple[FactProvenance, ...],
) -> tuple[FactProvenance, ...]:
    merged = _deduplicate((*current, *incoming))
    if len(merged) > 20:
        raise ClinicalStateError("CLINICAL_STATE_PROVENANCE_LIMIT_EXCEEDED")
    return merged


def _same_observation(left: ClinicalFact, right: ClinicalFact) -> bool:
    return left.category == right.category and left.value == right.value


def _merged_status(left: ClinicalFact, right: ClinicalFact) -> str:
    if "conflicted" in {left.status, right.status}:
        return "conflicted"
    if "confirmed" in {left.status, right.status}:
        return "confirmed"
    return "reported"


class DeterministicClinicalStateReducer:
    """Merge only validated user/tool observations into immutable state.

    A fact identifier is a semantic claim key. Repeated equal observations merge
    provenance; a different value under the same key preserves every candidate
    and marks all of them conflicted. No source can silently overwrite a
    conflict, including a later trusted-tool observation.
    """

    def reduce(
        self,
        current: ClinicalState,
        observations: tuple[ClinicalFact, ...],
        *,
        unknowns: tuple[BoundedClinicalText, ...] = (),
        resolved_unknowns: tuple[BoundedClinicalText, ...] = (),
    ) -> ClinicalState:
        facts = list(current.facts)
        conflicts = list(current.conflicts)

        for observation in observations:
            matching_indexes = [
                index for index, fact in enumerate(facts) if fact.fact_id == observation.fact_id
            ]
            equal_index = next(
                (
                    index
                    for index in matching_indexes
                    if _same_observation(facts[index], observation)
                ),
                None,
            )

            if equal_index is not None:
                existing = facts[equal_index]
                facts[equal_index] = existing.model_copy(
                    update={
                        "status": _merged_status(existing, observation),
                        "provenance": _merge_provenance(
                            existing.provenance,
                            observation.provenance,
                        ),
                    }
                )
            else:
                facts.append(observation)
                matching_indexes.append(len(facts) - 1)

            distinct_candidates = [
                facts[index]
                for index in matching_indexes
                if any(
                    not _same_observation(facts[index], facts[other_index])
                    for other_index in matching_indexes
                )
            ]
            if distinct_candidates:
                for index in matching_indexes:
                    facts[index] = facts[index].model_copy(update={"status": "conflicted"})
                conflicts.append(observation.fact_id)

        resolved = set(resolved_unknowns)
        observed_ids = {observation.fact_id for observation in observations}
        next_unknowns = _deduplicate(
            item
            for item in (*current.unknowns, *unknowns)
            if item not in resolved and item not in observed_ids
        )
        next_conflicts = _deduplicate(conflicts)

        try:
            return ClinicalState(
                facts=tuple(facts),
                unknowns=next_unknowns,
                conflicts=next_conflicts,
            )
        except ValidationError as exc:
            raise ClinicalStateError("CLINICAL_STATE_LIMIT_EXCEEDED") from exc
