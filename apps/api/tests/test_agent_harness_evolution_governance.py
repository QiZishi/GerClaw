"""Dual-track authority, mixed-candidate, and charter counterexamples."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.agent_harness.evolution_governance import (
    COMPONENT_CHARTERS,
    OBJECT_RULES,
    REQUIRED_CHARTERS_BY_OBJECT_KIND,
    CandidateChange,
    CandidateProposal,
    EvolutionGovernanceError,
    EvolutionGovernancePolicy,
    OnlineMutationRequest,
)

_BASE = "a" * 40
_CANDIDATE = "b" * 40
_DIGEST = "c" * 64


def _change(object_kind: str, target: str) -> CandidateChange:
    return CandidateChange(
        object_kind=object_kind,
        target=target,
        content_digest=_DIGEST,
    )


def _proposal(
    *changes: CandidateChange,
    declared_track: str,
) -> CandidateProposal:
    return CandidateProposal.model_validate(
        {
            "proposal_id": "candidate.unit-test",
            "declared_track": declared_track,
            "base_commit": _BASE,
            "candidate_commit": _CANDIDATE,
            "risk_level": "medium",
            "risk_reason_codes": ("test.review-required",),
            "activation_condition_ids": ("test.paired-evaluation",),
            "frozen_at": datetime.now(UTC),
            "changes": changes,
        }
    )


def test_preference_memory_classifies_online_at_presentation_authority() -> None:
    rule = EvolutionGovernancePolicy().classify_online_mutation(
        OnlineMutationRequest(
            object_kind="memory.preference",
            requested_authority="presentation_only",
            expected_revision=3,
        )
    )

    assert (rule.track, rule.update_policy, rule.owner) == (
        "mutable",
        "online_revisioned",
        "user",
    )
    assert rule.candidate_writable is True


def test_production_policy_manifest_cannot_be_replaced_by_constructor_injection() -> None:
    with pytest.raises(TypeError):
        EvolutionGovernancePolicy(rules=())  # type: ignore[call-arg]


def test_online_classifier_rejects_caller_supplied_ownership_claims() -> None:
    with pytest.raises(ValidationError, match="actor_owned"):
        OnlineMutationRequest(
            object_kind="memory.preference",
            requested_authority="presentation_only",
            expected_revision=3,
            actor_owned=True,  # type: ignore[call-arg]
        )


def test_preference_cannot_disguise_a_control_plane_authority_escalation() -> None:
    with pytest.raises(EvolutionGovernanceError) as caught:
        EvolutionGovernancePolicy().classify_online_mutation(
            OnlineMutationRequest(
                object_kind="memory.preference",
                requested_authority="control_plane",
                expected_revision=3,
            )
        )

    assert caught.value.code == "EVOLUTION_AUTHORITY_ESCALATION"


def test_immutable_candidate_still_requires_human_approval_when_global_flag_is_off() -> None:
    proposal = _proposal(
        _change("prompt.policy", "policy/prompt/candidate.json"),
        declared_track="immutable",
    )

    policy = EvolutionGovernancePolicy()
    policy.validate_candidate(proposal)
    assert policy.approval_required(
        proposal.declared_track,
        deployment_requires_approval=False,
    )
    assert not hasattr(policy, "assert_promotable")


def test_candidate_cannot_mix_mutable_skill_content_and_immutable_safety_policy() -> None:
    proposal = _proposal(
        _change("skill.presentation", "skill://presentation/patient-tone/v2"),
        _change("prompt.policy", "policy/prompt/safety.json"),
        declared_track="immutable",
    )

    with pytest.raises(EvolutionGovernanceError) as caught:
        EvolutionGovernancePolicy().validate_candidate(proposal)

    assert caught.value.code == "EVOLUTION_MIXED_TRACK_CANDIDATE"


def test_unknown_kind_defaults_to_immutable_and_cannot_mutate_online() -> None:
    policy = EvolutionGovernancePolicy()
    assert policy.rule_for("future.unknown").track == "immutable"
    with pytest.raises(EvolutionGovernanceError, match="EVOLUTION_ONLINE_CLASSIFICATION_FORBIDDEN"):
        policy.classify_online_mutation(
            OnlineMutationRequest(
                object_kind="future.unknown",
                requested_authority="control_plane",
                expected_revision=0,
            )
        )


def test_declared_mutable_kind_cannot_write_an_immutable_policy_target() -> None:
    proposal = _proposal(
        _change("skill.presentation", "policy/prompt/safety.json"),
        declared_track="mutable",
    )
    with pytest.raises(EvolutionGovernanceError) as caught:
        EvolutionGovernancePolicy().validate_candidate(proposal)
    assert caught.value.code == "EVOLUTION_TARGET_AUTHORITY_MISMATCH"


def test_sealed_assets_are_not_candidate_changes_even_with_approval() -> None:
    proposal = _proposal(
        _change("component.charter", "charters/runtime.json"),
        declared_track="immutable",
    )
    with pytest.raises(EvolutionGovernanceError) as caught:
        EvolutionGovernancePolicy().validate_candidate(proposal)
    assert caught.value.code == "EVOLUTION_SEALED_ASSET_FORBIDDEN"


@pytest.mark.parametrize(
    "target",
    ("../policy.json", "/etc/policy", "C:\\policy", "safe\\..\\policy"),
)
def test_candidate_target_rejects_traversal_and_absolute_paths(target: str) -> None:
    with pytest.raises(ValidationError, match="normalized relative target"):
        _change("prompt.policy", target)


def test_candidate_freeze_contract_rejects_same_commit_and_naive_time() -> None:
    valid = _proposal(
        _change("prompt.policy", "policy/prompt/candidate.json"),
        declared_track="immutable",
    ).model_dump()
    with pytest.raises(ValidationError, match="must differ"):
        CandidateProposal.model_validate({**valid, "candidate_commit": _BASE})
    with pytest.raises(ValidationError, match="timezone-aware"):
        CandidateProposal.model_validate(
            {**valid, "frozen_at": datetime.now().replace(tzinfo=None)}
        )


@pytest.mark.parametrize("missing", ("risk_reason_codes", "activation_condition_ids"))
def test_candidate_freeze_contract_requires_risk_and_activation(
    missing: str,
) -> None:
    valid = _proposal(
        _change("prompt.policy", "policy/prompt/candidate.json"),
        declared_track="immutable",
    ).model_dump()
    valid.pop(missing)
    with pytest.raises(ValidationError, match=missing):
        CandidateProposal.model_validate(valid)


def test_trusted_candidate_target_namespaces_do_not_overlap() -> None:
    prefixes = [
        prefix
        for rule in OBJECT_RULES
        if rule.candidate_writable
        for prefix in rule.allowed_target_prefixes
    ]

    assert len(prefixes) == len(set(prefixes))
    assert not any(
        left.startswith(right) or right.startswith(left)
        for index, left in enumerate(prefixes)
        for right in prefixes[index + 1 :]
    )


def test_every_core_component_has_a_candidate_non_writable_charter() -> None:
    expected = {
        "harness",
        "routing",
        "planning",
        "clinical_state",
        "context_snapshot",
        "run_lifecycle",
        "evidence",
        "plugin_runtime",
        "evolution_signals",
        "memory",
        "skill",
        "runtime",
    }

    assert {item.component for item in COMPONENT_CHARTERS} == expected
    assert all(
        item.candidate_readable and not item.candidate_writable for item in COMPONENT_CHARTERS
    )
    assert all(item.protected_mechanisms for item in COMPONENT_CHARTERS)


def test_offline_object_kinds_have_controller_owned_required_charters() -> None:
    offline_kinds = {
        rule.object_kind for rule in OBJECT_RULES if rule.update_policy == "offline_proposal_only"
    }
    known_charters = {
        evaluator_id
        for charter in COMPONENT_CHARTERS
        for evaluator_id in charter.sealed_evaluator_ids
    }

    assert set(REQUIRED_CHARTERS_BY_OBJECT_KIND) == offline_kinds
    assert all(
        required and set(required).issubset(known_charters)
        for required in REQUIRED_CHARTERS_BY_OBJECT_KIND.values()
    )
