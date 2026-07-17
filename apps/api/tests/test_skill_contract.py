"""Skill protocol surface must match design requirement §4.9."""

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
