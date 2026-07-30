"""Skill protocol surface must match design requirement §4.9."""

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.skill.offline_contracts import SkillReviewEventAppend
from gerclaw_api.modules.skill.protocols import SkillModule


def test_skill_exposes_registry_execution_and_generation_methods() -> None:
    for name in (
        "list_skills",
        "load_skill",
        "register_skill",
        "execute_skill",
        "generate_skill_from_nl",
        "evolve_skill_from_nl",
    ):
        assert hasattr(SkillModule, name)


def test_offline_review_events_are_content_free_and_activation_consumes_ticket() -> None:
    activated = SkillReviewEventAppend(
        event_type="activated",
        artifact_sha256="a" * 64,
        approval_ticket_digest="b" * 64,
    )

    assert activated.reason_codes == ()
    with pytest.raises(ValidationError, match="approval ticket"):
        SkillReviewEventAppend(
            event_type="activated",
            artifact_sha256="a" * 64,
        )
    with pytest.raises(ValidationError, match="stable identifiers"):
        SkillReviewEventAppend(
            event_type="paired_rejected",
            artifact_sha256="a" * 64,
            reason_codes=("contains user text",),
        )
