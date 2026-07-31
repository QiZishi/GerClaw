"""Operator-only composition for encrypted Skill review and atomic activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gerclaw_api.modules.skill.offline_activation import (
    SkillActivationOutcome,
    SkillOfflineActivator,
)
from gerclaw_api.modules.skill.offline_contracts import SkillProposalExportEnvelope
from pydantic import BaseModel, ConfigDict

from gerclaw_evolution.approval import HumanApprovalProof
from gerclaw_evolution.attestation import SealedGateAttestation
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import (
    PairedEvaluationGate,
    PairedEvaluationReport,
)
from gerclaw_evolution.git_repository import GitRepository
from gerclaw_evolution.skill_authorization import SkillActivationAuthorizer
from gerclaw_evolution.skill_proposal import SkillProposalEnvelopeOpener
from gerclaw_evolution.skill_runner import SubprocessSkillPairedRunner

_STRICT = ConfigDict(extra="forbid", frozen=True)


class PreparedSkillReviewPackage(BaseModel):
    """Encrypted candidate handoff plus content-free reproducible public report."""

    model_config = _STRICT

    schema_version: Literal["prepared-skill-review-package-v1"] = "prepared-skill-review-package-v1"
    envelope: SkillProposalExportEnvelope
    paired_report: PairedEvaluationReport


@dataclass(frozen=True, slots=True)
class SkillReviewOperator:
    """Re-run exact public gates before consuming sealed and human artifacts."""

    opener: SkillProposalEnvelopeOpener
    paired_runner: SubprocessSkillPairedRunner
    activation_authorizer: SkillActivationAuthorizer | None = None
    offline_activator: SkillOfflineActivator | None = None

    def pair(
        self,
        repository: GitRepository,
        envelope: SkillProposalExportEnvelope,
    ) -> PreparedSkillReviewPackage:
        candidate = self.opener.open(envelope)
        baseline = self.paired_runner.run(
            repository,
            candidate=candidate,
            role="baseline",
        )
        evolved = self.paired_runner.run(
            repository,
            candidate=candidate,
            role="candidate",
        )
        report = PairedEvaluationGate().compare(
            candidate.frozen,
            baseline,
            evolved,
        )
        return PreparedSkillReviewPackage(
            envelope=envelope,
            paired_report=report,
        )

    async def activate(
        self,
        repository: GitRepository,
        package: PreparedSkillReviewPackage,
        *,
        sealed_attestation: SealedGateAttestation,
        human_approval: HumanApprovalProof,
    ) -> SkillActivationOutcome:
        if self.activation_authorizer is None or self.offline_activator is None:
            raise CandidateControlError("EVOLUTION_SKILL_OPERATOR_ACTIVATION_UNAVAILABLE")
        reproduced = self.pair(repository, package.envelope)
        original = package.paired_report
        rerun = reproduced.paired_report
        if (
            not original.gate.passed
            or not rerun.gate.passed
            or original.proposal_id != rerun.proposal_id
            or original.base_commit != rerun.base_commit
            or original.candidate_commit != rerun.candidate_commit
            or original.frozen_manifest_sha256 != rerun.frozen_manifest_sha256
            or original.baseline.runner_id != rerun.baseline.runner_id
            or original.baseline.runner_version != rerun.baseline.runner_version
            or original.baseline.evaluation_profile_sha256
            != rerun.baseline.evaluation_profile_sha256
            or original.baseline.execution_bundle_sha256 != rerun.baseline.execution_bundle_sha256
            or {item.case_id for item in original.candidate.cases}
            != {item.case_id for item in rerun.candidate.cases}
            or {item.evaluator_id for item in original.candidate.charters}
            != {item.evaluator_id for item in rerun.candidate.charters}
        ):
            raise CandidateControlError("EVOLUTION_SKILL_OPERATOR_REPORT_MISMATCH")
        candidate = self.opener.open(package.envelope)
        authorization = self.activation_authorizer.authorize(
            candidate,
            report=original,
            sealed_attestation=sealed_attestation,
            human_approval=human_approval,
        )
        return await self.offline_activator.activate(authorization)
