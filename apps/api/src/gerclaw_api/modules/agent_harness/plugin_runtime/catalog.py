"""Allowlisted GerClaw capability catalog and deterministic selection."""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from gerclaw_api.modules.agent_harness.plugin_runtime.contracts import (
    CapabilityEntrypoint,
    CapabilitySelection,
    CapabilitySelectionMode,
    PluginManifest,
    PluginRuntimeError,
    SelectedCapability,
    capability_contract_schemas,
)
from gerclaw_api.modules.workflows import WorkflowId

GERCLAW_CAPABILITY_MANIFESTS: tuple[PluginManifest, ...] = (
    PluginManifest(
        capability_id="gerclaw.cga",
        version="1.0.0",
        display_name="老年综合评估",
        risk_level="medium",
        owner_module="cga",
        entrypoint=CapabilityEntrypoint.CGA_ASSESSMENT,
        automatic_selection=True,
        supported_workflows=("standard", "cga"),
        shared_result_kinds=("attachment_projection", "clinical_observation"),
        input_schema=capability_contract_schemas()[0],
        output_schema=capability_contract_schemas()[1],
    ),
    PluginManifest(
        capability_id="gerclaw.medication_review",
        version="1.0.0",
        display_name="用药审查",
        risk_level="high",
        owner_module="medication_review",
        entrypoint=CapabilityEntrypoint.MEDICATION_REVIEW_INTAKE,
        automatic_selection=True,
        supported_workflows=("standard",),
        shared_result_kinds=("clinical_observation",),
        input_schema=capability_contract_schemas()[0],
        output_schema=capability_contract_schemas()[1],
    ),
    PluginManifest(
        capability_id="gerclaw.five_prescription",
        version="1.0.0",
        display_name="五大处方",
        risk_level="high",
        owner_module="prescription",
        entrypoint=CapabilityEntrypoint.FIVE_PRESCRIPTION_INTAKE,
        automatic_selection=True,
        supported_workflows=("standard", "prescription"),
        shared_result_kinds=(
            "attachment_projection",
            "clinical_observation",
            "local_evidence",
        ),
        input_schema=capability_contract_schemas()[0],
        output_schema=capability_contract_schemas()[1],
    ),
    PluginManifest(
        capability_id="gerclaw.report_artifact",
        version="1.0.0",
        display_name="可编辑报告",
        risk_level="medium",
        owner_module="run_artifact",
        entrypoint=CapabilityEntrypoint.RUN_ARTIFACT,
        automatic_selection=True,
        supported_workflows=("standard", "cga", "prescription"),
        shared_result_kinds=("local_evidence", "clinical_observation"),
        input_schema=capability_contract_schemas()[0],
        output_schema=capability_contract_schemas()[1],
    ),
)

_AUTO_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "gerclaw.cga",
        re.compile(r"(?:\bCGA\b|老年综合评估|老年评估|做.{0,4}量表)", re.IGNORECASE),
    ),
    (
        "gerclaw.medication_review",
        re.compile(r"(?:用药审查|药物审查|药物相互作用|核对.{0,6}用药)"),
    ),
    (
        "gerclaw.five_prescription",
        re.compile(r"(?:五大处方|生成.{0,6}处方|处方生成)"),
    ),
    (
        "gerclaw.report_artifact",
        re.compile(r"(?:生成|形成|撰写|整理).{0,12}(?:报告|文档)"),
    ),
)

_WORKFLOW_DEFAULTS = {
    WorkflowId.CGA: "gerclaw.cga",
    WorkflowId.PRESCRIPTION: "gerclaw.five_prescription",
}


class GovernedCapabilityCatalog:
    """Select only reviewed manifests without invoking their owner modules."""

    def __init__(
        self,
        manifests: Iterable[PluginManifest] = GERCLAW_CAPABILITY_MANIFESTS,
    ) -> None:
        self._manifests: dict[str, PluginManifest] = {}
        for manifest in manifests:
            if manifest.entrypoint is None:
                raise PluginRuntimeError(f"CAPABILITY_ENTRYPOINT_MISSING:{manifest.capability_id}")
            if manifest.capability_id in self._manifests:
                raise PluginRuntimeError(f"CAPABILITY_DUPLICATE:{manifest.capability_id}")
            self._manifests[manifest.capability_id] = manifest

    def manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(self._manifests.values())

    def resolve(self, capability_id: str) -> PluginManifest:
        manifest = self._manifests.get(capability_id)
        if manifest is None:
            raise PluginRuntimeError(f"CAPABILITY_UNKNOWN:{capability_id}")
        return manifest

    def select(
        self,
        *,
        message: str,
        workflow: WorkflowId | str,
        requested: tuple[str, ...] = (),
    ) -> CapabilitySelection:
        """Combine manual, workflow, and automatic choices under one allowlist."""

        normalized_workflow = WorkflowId(workflow)
        sources: dict[str, CapabilitySelectionMode] = {}
        for capability_id in requested:
            manifest = self.resolve(capability_id)
            if not manifest.manual_selection:
                raise PluginRuntimeError(f"CAPABILITY_MANUAL_SELECTION_DISABLED:{capability_id}")
            self._require_workflow(manifest, normalized_workflow)
            sources.setdefault(capability_id, CapabilitySelectionMode.MANUAL)

        workflow_capability = _WORKFLOW_DEFAULTS.get(normalized_workflow)
        if workflow_capability is not None:
            sources.setdefault(workflow_capability, CapabilitySelectionMode.WORKFLOW)

        for capability_id, pattern in _AUTO_TRIGGERS:
            manifest = self.resolve(capability_id)
            if (
                manifest.automatic_selection
                and normalized_workflow.value in manifest.supported_workflows
                and pattern.search(message)
            ):
                sources.setdefault(capability_id, CapabilitySelectionMode.AUTOMATIC)

        selected: list[SelectedCapability] = []
        for capability_id, source in sources.items():
            manifest = self.resolve(capability_id)
            self._require_workflow(manifest, normalized_workflow)
            if manifest.entrypoint is None:  # pragma: no cover - constructor invariant
                raise PluginRuntimeError(f"CAPABILITY_ENTRYPOINT_MISSING:{capability_id}")
            selected.append(
                SelectedCapability(
                    capability_id=capability_id,
                    source=source,
                    entrypoint=manifest.entrypoint,
                    owner_module=manifest.owner_module,
                )
            )
        return CapabilitySelection(selected=tuple(selected))

    @staticmethod
    def _require_workflow(
        manifest: PluginManifest,
        workflow: WorkflowId,
    ) -> None:
        if workflow.value not in manifest.supported_workflows:
            raise PluginRuntimeError(
                f"CAPABILITY_WORKFLOW_UNSUPPORTED:{manifest.capability_id}:{workflow.value}"
            )


@lru_cache(maxsize=1)
def get_default_capability_catalog() -> GovernedCapabilityCatalog:
    return GovernedCapabilityCatalog()
