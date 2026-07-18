"""Workflow registration and security-profile gates are executable Runtime policy."""

from __future__ import annotations

import pytest

from gerclaw_api.domain.chat_schemas import ChatRequest
from gerclaw_api.modules.security_evaluation import (
    SecurityControl,
    SecurityProfileRegistry,
)
from gerclaw_api.modules.workflows import (
    WORKFLOW_DEFINITIONS,
    WorkflowContextError,
    WorkflowId,
    WorkflowRegistry,
    get_default_workflow_registry,
)
from gerclaw_api.modules.workflows.profiles import WORKFLOW_SECURITY_PROFILES


def test_registered_workflows_have_exact_active_security_profiles() -> None:
    registry = get_default_workflow_registry()

    standard = registry.validate_context(
        WorkflowId.STANDARD,
        loaded_skill_count=1,
        uploaded_file_count=1,
    )
    companion = registry.validate_context(
        WorkflowId.COMPANION,
        loaded_skill_count=0,
        uploaded_file_count=0,
    )
    prescription = registry.validate_context(
        WorkflowId.PRESCRIPTION,
        loaded_skill_count=0,
        uploaded_file_count=10,
    )

    assert standard.version == "1.0.0"
    assert standard.search_enabled is True
    assert companion.owner_module == "companion"
    assert companion.search_enabled is False
    assert prescription.owner_module == "prescription"
    assert prescription.risk_level.value == "high"


def test_prescription_workflow_rejects_skills_but_accepts_its_bounded_documents() -> None:
    registry = get_default_workflow_registry()

    with pytest.raises(WorkflowContextError, match="does not accept Skills or uploaded files"):
        registry.validate_context(
            WorkflowId.PRESCRIPTION,
            loaded_skill_count=1,
            uploaded_file_count=0,
        )

    assert registry.validate_context(
        WorkflowId.PRESCRIPTION,
        loaded_skill_count=0,
        uploaded_file_count=10,
    ).accepts_uploaded_files


@pytest.mark.parametrize(
    ("skills", "files"),
    [(1, 0), (0, 1), (2, 3)],
)
def test_companion_context_is_rejected_by_the_server_owned_registry(
    skills: int, files: int
) -> None:
    with pytest.raises(WorkflowContextError, match="does not accept Skills or uploaded files"):
        get_default_workflow_registry().validate_context(
            WorkflowId.COMPANION,
            loaded_skill_count=skills,
            uploaded_file_count=files,
        )


def test_missing_workflow_security_profile_fails_closed() -> None:
    registry = WorkflowRegistry(
        WORKFLOW_DEFINITIONS,
        security_profiles=SecurityProfileRegistry(),
    )

    with pytest.raises(WorkflowContextError, match="security profile"):
        registry.resolve(WorkflowId.STANDARD)


@pytest.mark.parametrize(
    ("workflow_id", "missing_control"),
    [
        (WorkflowId.STANDARD, SecurityControl.EVIDENCE_PROVENANCE),
        (WorkflowId.PRESCRIPTION, SecurityControl.EXTERNAL_EGRESS_REDACTION),
        (WorkflowId.CGA, SecurityControl.PATIENT_OWNERSHIP),
        (WorkflowId.COMPANION, SecurityControl.INPUT_SCHEMA),
    ],
)
def test_workflow_profile_missing_executable_control_fails_closed(
    workflow_id: WorkflowId,
    missing_control: SecurityControl,
) -> None:
    profiles = tuple(
        profile.model_copy(
            update={"required_controls": profile.required_controls - {missing_control}}
        )
        if profile.asset_name == workflow_id.value
        else profile
        for profile in WORKFLOW_SECURITY_PROFILES
    )
    registry = WorkflowRegistry(
        WORKFLOW_DEFINITIONS, security_profiles=SecurityProfileRegistry(profiles)
    )

    with pytest.raises(WorkflowContextError, match="security profile"):
        registry.resolve(workflow_id)


def test_chat_contract_uses_the_same_workflow_context_gate() -> None:
    with pytest.raises(ValueError, match="workflow does not accept Skills or uploaded files"):
        ChatRequest.model_validate(
            {
                "session_id": "f9b7551d-5d43-47b6-9d91-1c10384e8e12",
                "message": "我有点孤单",
                "workflow": "companion",
                "loaded_skills": ["skill_sample_12345678"],
            }
        )
