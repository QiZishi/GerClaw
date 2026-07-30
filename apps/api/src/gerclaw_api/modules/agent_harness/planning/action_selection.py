"""SAVI-style ordinal action selection with safety and validity gates."""

from __future__ import annotations

from gerclaw_api.modules.agent_harness.planning.contracts import (
    ActionCandidate,
    ActionKind,
    ActionSelection,
    RankedAction,
)


class SAVIActionSelector:
    """Rank actions without pretending to know calibrated probabilities."""

    def __init__(self, *, minimum_score: int) -> None:
        self._minimum_score = minimum_score

    def select(self, candidates: tuple[ActionCandidate, ...]) -> ActionSelection:
        rejected = tuple(
            candidate.action_id
            for candidate in candidates
            if not candidate.catalog_valid or candidate.already_known
        )
        eligible = [
            candidate
            for candidate in candidates
            if candidate.catalog_valid and not candidate.already_known
        ]
        mandatory = [
            candidate
            for candidate in eligible
            if candidate.safety_required or candidate.treatment_prerequisite
        ]
        pool = mandatory or eligible
        if not pool:
            return ActionSelection(
                rejected_action_ids=rejected,
                should_stop=True,
                reason_code="no_valid_action",
            )

        ranked = sorted(
            (RankedAction(candidate=candidate, score=self._score(candidate)) for candidate in pool),
            key=lambda item: (
                item.score,
                item.candidate.kind is ActionKind.ASK,
                item.candidate.kind is ActionKind.EXAM,
                item.candidate.action_id,
            ),
            reverse=True,
        )
        selected = ranked[0]
        if mandatory:
            return ActionSelection(
                selected=selected,
                rejected_action_ids=rejected,
                should_stop=False,
                reason_code="mandatory_prerequisite",
            )
        if selected.score < self._minimum_score:
            answer = next(
                (item for item in ranked if item.candidate.kind is ActionKind.ANSWER),
                None,
            )
            return ActionSelection(
                selected=answer,
                rejected_action_ids=rejected,
                should_stop=True,
                reason_code="marginal_value_below_threshold",
            )
        return ActionSelection(
            selected=selected,
            rejected_action_ids=rejected,
            should_stop=selected.candidate.kind is ActionKind.ANSWER,
            reason_code=(
                "answer_ready"
                if selected.candidate.kind is ActionKind.ANSWER
                else "highest_ordinal_value"
            ),
        )

    @staticmethod
    def _score(candidate: ActionCandidate) -> int:
        return (
            candidate.diagnostic_gain
            + candidate.comorbidity_gain
            + candidate.treatment_gain
            + candidate.safety_gain
            - candidate.token_cost
            - candidate.action_cost
            - candidate.invasiveness
            - candidate.redundancy
        )
