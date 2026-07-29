"""Dependency-injection bundle for independently replaceable Harness components."""

from dataclasses import dataclass

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalStateReducer
from gerclaw_api.modules.agent_harness.context_snapshot import ContextSnapshotAssembler
from gerclaw_api.modules.agent_harness.evidence import EvidenceValidator
from gerclaw_api.modules.agent_harness.evolution_signals import EvolutionSignalSink
from gerclaw_api.modules.agent_harness.planning import Planner
from gerclaw_api.modules.agent_harness.plugin_runtime import PluginRuntime
from gerclaw_api.modules.agent_harness.routing import Router
from gerclaw_api.modules.agent_harness.run_lifecycle import RunLifecycle


@dataclass(frozen=True, slots=True)
class HarnessComponents:
    """Optional component ports activated only by their owning implementation stage."""

    router: Router | None = None
    planner: Planner | None = None
    clinical_state_reducer: ClinicalStateReducer | None = None
    context_snapshot_assembler: ContextSnapshotAssembler | None = None
    run_lifecycle: RunLifecycle | None = None
    evidence_validator: EvidenceValidator | None = None
    plugin_runtime: PluginRuntime | None = None
    evolution_signal_sink: EvolutionSignalSink | None = None
