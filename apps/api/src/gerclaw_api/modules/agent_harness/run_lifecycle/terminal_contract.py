"""Pre-publication validation for a completely assembled answer candidate."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from gerclaw_api.modules.agent_harness.evidence import BoundTurnEvidence, bind_turn_evidence
from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import AgentStreamResult
from gerclaw_api.modules.agent_harness.safety import (
    MEDICAL_DISCLAIMER,
    PATIENT_CLINICAL_RISK_NOTICE,
    requires_patient_clinical_risk_notice,
    safety_decision,
)
from gerclaw_api.modules.contracts import AgentResponse, Citation
from gerclaw_api.modules.validation.contracts import ModelOutputContractValidationError


class UnboundClinicalClaimsError(ModelOutputContractValidationError):
    """Compatibility error for callers that explicitly request claim repair."""

    def __init__(self, claim_ids: tuple[str, ...]) -> None:
        super().__init__("candidate contains clinical claims without admitted evidence")
        self.claim_ids = claim_ids


def validate_terminal_response_candidate(
    result: AgentStreamResult,
    *,
    initial_local: list[Citation],
    additional_local: list[Citation],
    web: list[Citation],
    attachments: list[Citation],
    is_clinical_claim: Callable[[str], bool],
    high_risk_codes: list[str],
    medical_content: bool,
    patient_facing: bool,
) -> BoundTurnEvidence:
    """Assemble a terminal answer without making citation coverage a hard gate.

    Evidence is still bound and audited whenever it exists.  Missing evidence
    is represented by an empty citation list and handled as a degraded answer,
    rather than discarding an otherwise useful model response.
    """

    bound = bind_turn_evidence(
        result.text,
        initial_local=initial_local,
        additional_local=additional_local,
        web=web,
        attachments=attachments,
        is_clinical_claim=is_clinical_claim,
        markers_already_bound=True,
        adopted_only=True,
    )
    claims_complete = bound.claim_audit.all_clinical_claims_bound
    patient_notice = patient_facing and requires_patient_clinical_risk_notice(bound.text)
    risk_delta = f"\n\n{PATIENT_CLINICAL_RISK_NOTICE}" if patient_notice else ""
    disclaimer_delta = f"{risk_delta}\n\n{MEDICAL_DISCLAIMER}" if medical_content else risk_delta
    try:
        AgentResponse(
            text=f"{bound.text}{disclaimer_delta}",
            citations=list(bound.citations),
            safety=safety_decision(
                high_risk_codes,
                medical_content=medical_content,
                deterministic_diagnosis_blocked=result.deterministic_diagnosis_blocked,
                evidence_backed_clinical_conclusion_allowed=claims_complete,
                patient_clinical_risk_notice_applied=patient_notice,
            ),
            medical_content=medical_content,
            structured={
                "model_invoked": True,
                "evidence_backed_clinical_conclusion": claims_complete,
            },
        )
    except ValidationError as error:
        raise ModelOutputContractValidationError(
            "candidate answer violates the public response contract"
        ) from error
    return bound
