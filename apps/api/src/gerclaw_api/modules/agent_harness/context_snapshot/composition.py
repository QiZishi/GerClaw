"""Composition helper that keeps context policy inside its owning component."""

from __future__ import annotations

from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.context_snapshot.models import (
    AgentContext,
    ContextSnapshotAssembler,
    ContextSnapshotError,
    ConversationHistoryMessage,
)
from gerclaw_api.modules.contracts import ExecutionContext


@dataclass(frozen=True, slots=True)
class ContextSnapshotInputs:
    """Already authorized inputs used to build or restore one exact snapshot."""

    execution: ExecutionContext
    history: tuple[ConversationHistoryMessage, ...]
    profile_context: str
    profile_version: int
    memory_refs: tuple[str, ...]
    session_summary: str
    clinical_state: ClinicalState
    loaded_skills: tuple[str, ...]
    uploaded_files: tuple[str, ...]
    companion: bool
    quick_route: bool
    search_available: bool
    skill_available: bool
    preassembled: AgentContext | None = None


def compose_context_snapshot(
    assembler: ContextSnapshotAssembler,
    inputs: ContextSnapshotInputs,
) -> AgentContext:
    """Restore a frozen snapshot or assemble one using stable policy ids."""

    if inputs.preassembled is not None:
        if inputs.preassembled.execution != inputs.execution:
            raise ContextSnapshotError("persisted Agent context does not match execution identity")
        if tuple(inputs.preassembled.loaded_skills) != inputs.loaded_skills:
            raise ContextSnapshotError("persisted Agent context does not match frozen Skills")
        if tuple(inputs.preassembled.uploaded_files) != inputs.uploaded_files:
            raise ContextSnapshotError("persisted Agent context does not match frozen documents")
        return inputs.preassembled

    tool_names = (
        [] if inputs.companion or inputs.quick_route else ["search_knowledge", "search_memory"]
    )
    if not inputs.companion and not inputs.quick_route and inputs.search_available:
        tool_names.append("web_search")
    if not inputs.companion and not inputs.quick_route and inputs.skill_available:
        tool_names.append("Skill")
    return assembler.assemble(
        execution=inputs.execution,
        system_instructions=(
            ("companion_safety_v1", "no_raw_chain_of_thought_v1")
            if inputs.companion
            else (
                "medical_safety_v1",
                "traceable_evidence_required_v1",
                "no_raw_chain_of_thought_v1",
            )
        ),
        tool_names=tuple(tool_names),
        profile_ref=(
            f"health_profile:v{inputs.profile_version}" if inputs.profile_version else None
        ),
        profile_context=inputs.profile_context,
        profile_version=inputs.profile_version,
        memory_refs=inputs.memory_refs,
        session_summary=inputs.session_summary,
        clinical_state=inputs.clinical_state,
        loaded_skills=inputs.loaded_skills,
        uploaded_files=inputs.uploaded_files,
        history=inputs.history,
    )
