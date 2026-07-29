"""Production SAVI selection and C3 direction preparation."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from gerclaw_api.modules.agent_harness.clinical_state import (
    C3DifferentialValidator,
    ClinicalState,
    DifferentialAssessment,
    DifferentialCandidate,
    DifferentialPriority,
)
from gerclaw_api.modules.agent_harness.planning.action_selection import (
    SAVIActionSelector,
)
from gerclaw_api.modules.agent_harness.planning.contracts import (
    ActionCandidate,
    ActionKind,
    ActionSelection,
)

_DIAGNOSTIC_INTENT = re.compile(r"什么原因|可能是什么|鉴别|诊断|怎么回事")
_TREATMENT_INTENT = re.compile(
    r"用药|处方|治疗|停药|换药|改药|剂量|加药|减药|药物调整"
)


class TurnClinicalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_selection: ActionSelection
    differential_assessment: DifferentialAssessment = DifferentialAssessment()
    clarification_questions: tuple[str, ...] = Field(default=(), max_length=20)


class ClinicalDecisionCoordinator:
    """Choose ASK/EXAM/ANSWER and validate any diagnostic-direction context."""

    def __init__(self, *, minimum_score: int) -> None:
        self._selector = SAVIActionSelector(minimum_score=minimum_score)
        self._c3 = C3DifferentialValidator()

    def prepare(
        self,
        *,
        state: ClinicalState,
        message: str,
        has_attachments: bool,
    ) -> TurnClinicalDecision:
        diagnostic_intent = _DIAGNOSTIC_INTENT.search(message) is not None
        treatment_intent = _TREATMENT_INTENT.search(message) is not None
        clarification_questions = self._clarification_questions(
            state,
            diagnostic_intent=diagnostic_intent,
            treatment_intent=treatment_intent,
        )
        candidates: list[ActionCandidate] = [
            ActionCandidate(
                action_id="answer_current_question",
                kind=ActionKind.ANSWER,
                public_summary="根据当前已核验信息整理回答",
                diagnostic_gain=1,
                treatment_gain=1,
                token_cost=1,
            )
        ]
        if clarification_questions:
            candidates.append(
                ActionCandidate(
                    action_id="ask_clinical_unknowns",
                    kind=ActionKind.ASK,
                    public_summary="先确认影响判断的关键信息",
                    hypothesis_links=("clinical_unknowns",),
                    treatment_prerequisite=treatment_intent,
                    diagnostic_gain=2,
                    treatment_gain=3 if treatment_intent else 0,
                    safety_gain=2,
                    action_cost=1,
                )
            )
        if has_attachments:
            candidates.append(
                ActionCandidate(
                    action_id="examine_uploaded_material",
                    kind=ActionKind.EXAM,
                    public_summary="先核对本轮上传资料",
                    hypothesis_links=("uploaded_material",),
                    diagnostic_gain=2,
                    treatment_gain=1,
                    token_cost=1,
                    action_cost=1,
                )
            )
        selection = self._selector.select(tuple(candidates))
        assessment = (
            self._prepare_differential(state, clarification_questions)
            if diagnostic_intent
            else DifferentialAssessment()
        )
        return TurnClinicalDecision(
            action_selection=selection,
            differential_assessment=self._c3.validate(state, assessment),
            clarification_questions=clarification_questions,
        )

    @staticmethod
    def _clarification_questions(
        state: ClinicalState,
        *,
        diagnostic_intent: bool,
        treatment_intent: bool,
    ) -> tuple[str, ...]:
        if not diagnostic_intent and not treatment_intent:
            return ()
        usable = tuple(fact for fact in state.facts if fact.status != "conflicted")

        def has_category(*categories: str) -> bool:
            return any(fact.category in categories for fact in usable)

        questions = list(state.unknowns)
        if treatment_intent:
            prerequisites = (
                ("年龄", has_category("demographic"), ("年龄",)),
                (
                    "药物过敏史(包括明确无药物过敏)",
                    has_category("allergy")
                    or any(
                        fact.category == "negative_evidence"
                        and "过敏" in str(fact.value)
                        for fact in usable
                    ),
                    ("过敏",),
                ),
                (
                    "完整当前用药名称、剂量和频次",
                    has_category("medication"),
                    ("用药", "药物", "剂量"),
                ),
                (
                    "重要基础病以及近期肝肾功能情况",
                    has_category("history", "test"),
                    ("基础病", "肝肾", "合并症"),
                ),
            )
            for question, satisfied, markers in prerequisites:
                if satisfied:
                    questions = [
                        item
                        for item in questions
                        if not any(marker in item for marker in markers)
                    ]
                elif question not in questions:
                    questions.append(question)
        elif diagnostic_intent:
            if not has_category("timeline"):
                questions.append("症状开始时间、持续时间和变化过程")
            questions.append("伴随症状、诱发或缓解因素")
        return tuple(dict.fromkeys(questions))[:20]

    @staticmethod
    def _prepare_differential(
        state: ClinicalState,
        clarification_questions: tuple[str, ...],
    ) -> DifferentialAssessment:
        supporting = next(
            (
                fact
                for fact in reversed(state.facts)
                if fact.category in {"chief_complaint", "symptom"}
                and fact.status != "conflicted"
            ),
            None,
        )
        if supporting is None:
            return DifferentialAssessment()
        return DifferentialAssessment(
            candidates=(
                DifferentialCandidate(
                    candidate_id="reported_symptom_direction",
                    label="基于当前自述的症状原因待评估方向",
                    priority=DifferentialPriority.CONSIDER,
                    supporting_fact_ids=(supporting.fact_id,),
                    missing_information=(
                        clarification_questions
                        if clarification_questions
                        else ("症状时间线、伴随表现和影响因素",)
                    ),
                ),
            )
        )
