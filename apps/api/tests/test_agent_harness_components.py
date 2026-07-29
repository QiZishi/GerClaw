"""Independent construction tests for Agent Harness component boundaries."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.agent_harness import HarnessComponents, ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness.clinical_state import (
    ClinicalFact,
    ClinicalState,
    FactProvenance,
)
from gerclaw_api.modules.agent_harness.evidence import EvidenceRecord
from gerclaw_api.modules.agent_harness.evolution_signals import EvolutionSignal
from gerclaw_api.modules.agent_harness.planning import DynamicPlan, PlanNode
from gerclaw_api.modules.agent_harness.plugin_runtime import PluginManifest
from gerclaw_api.modules.agent_harness.routing import (
    RouteDecision,
    RouteKind,
    RoutingInput,
)
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    CanonicalTextStream,
    SafeSentenceBuffer,
)

_COMPONENTS = (
    "routing",
    "planning",
    "clinical_state",
    "context_snapshot",
    "run_lifecycle",
    "evidence",
    "plugin_runtime",
    "evolution_signals",
)


def test_every_component_has_agent_instructions_and_reader_documentation() -> None:
    root = (
        Path(__file__).parents[1]
        / "src"
        / "gerclaw_api"
        / "modules"
        / "agent_harness"
    )

    for component in _COMPONENTS:
        assert (root / component / "AGENTS.md").is_file()
        assert (root / component / "README.md").is_file()


def test_root_harness_is_a_small_compatibility_facade() -> None:
    root = (
        Path(__file__).parents[1]
        / "src"
        / "gerclaw_api"
        / "modules"
        / "agent_harness"
    )
    facade = (root / "harness.py").read_text(encoding="utf-8")

    assert len(facade.splitlines()) <= 100
    for concrete_owner in (
        "FailoverChatModel",
        "HybridRAGModule",
        "ProductionMemoryModule",
        "GovernedToolRegistry",
    ):
        assert concrete_owner not in facade


def test_component_packages_do_not_read_environment_directly() -> None:
    root = (
        Path(__file__).parents[1]
        / "src"
        / "gerclaw_api"
        / "modules"
        / "agent_harness"
    )

    for component in _COMPONENTS:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / component).glob("*.py")
        )
        assert "os.getenv(" not in source
        assert "os.environ[" not in source


def test_component_injection_bundle_is_independently_constructible() -> None:
    components = HarnessComponents()

    assert components.router is None
    assert components.evolution_signal_sink is None


def test_routing_contract_is_versioned_and_forbids_unknown_fields() -> None:
    routing_input = RoutingInput(message="今天心情不错")
    decision = RouteDecision(
        route=RouteKind.QUICK,
        reason_code="non_medical_simple",
    )

    assert routing_input.schema_version == "1.0"
    assert decision.route is RouteKind.QUICK
    with pytest.raises(ValidationError, match="emergency"):
        RouteDecision(
            route=RouteKind.EMERGENCY,
            reason_code="red_flag",
        )
    with pytest.raises(ValidationError):
        RoutingInput(message="hello", unexpected=True)  # type: ignore[call-arg]


def test_resolved_config_is_validated_and_immutable() -> None:
    config = ResolvedHarnessConfig(
        max_react_iterations=6,
        max_output_characters=20_000,
        max_output_bytes=80_000,
        evidence_top_k=8,
        memory_top_k=5,
        memory_min_score=0.6,
        approval_ttl_seconds=900,
        context_trigger_ratio=0.85,
        context_reserve_ratio=0.2,
    )

    assert config.max_react_iterations == 6
    with pytest.raises(ValidationError):
        ResolvedHarnessConfig(
            max_react_iterations=0,
            max_output_characters=20_000,
            max_output_bytes=80_000,
            evidence_top_k=8,
            memory_top_k=5,
            memory_min_score=0.6,
            approval_ttl_seconds=900,
            context_trigger_ratio=0.85,
            context_reserve_ratio=0.2,
        )


def test_dynamic_plan_rejects_unknown_and_self_references() -> None:
    with pytest.raises(ValidationError, match="itself"):
        PlanNode(
            node_id="search",
            dependencies=("search",),
            capability="rag.search",
            public_summary="正在检索资料",
        )

    with pytest.raises(ValidationError, match="unknown nodes"):
        DynamicPlan(
            nodes=(
                PlanNode(
                    node_id="answer",
                    dependencies=("missing",),
                    capability="answer.compose",
                    public_summary="正在整理回答",
                ),
            )
        )

    with pytest.raises(ValidationError, match="acyclic"):
        DynamicPlan(
            nodes=(
                PlanNode(
                    node_id="first",
                    dependencies=("second",),
                    capability="test.first",
                    public_summary="第一步",
                ),
                PlanNode(
                    node_id="second",
                    dependencies=("first",),
                    capability="test.second",
                    public_summary="第二步",
                ),
            )
        )


def test_clinical_state_requires_trusted_provenance() -> None:
    provenance = FactProvenance(
        source_type="user",
        source_id="message-1",
        observed_at=datetime.now(UTC),
    )
    state = ClinicalState(
        facts=(
            ClinicalFact(
                fact_id="symptom-1",
                category="symptom",
                value="头晕",
                status="reported",
                provenance=(provenance,),
            ),
        ),
        unknowns=("持续时间",),
    )

    assert state.facts[0].status == "reported"
    assert state.unknowns == ("持续时间",)


def test_evidence_and_plugin_contracts_keep_capability_owners_external() -> None:
    evidence = EvidenceRecord(
        evidence_id="E1",
        source_type="knowledge_base",
        title="测试指南",
        status="verified",
        locator="section-1",
        adopted_text="用于合同测试的文本",
        applicability="仅用于测试",
    )
    manifest = PluginManifest(
        capability_id="gerclaw.cga",
        version="1.0.0",
        display_name="老年综合评估",
        risk_level="medium",
        required_tools=("cga.read",),
    )

    assert evidence.adopted_text
    assert manifest.required_tools == ("cga.read",)
    unavailable = EvidenceRecord(
        evidence_id="E2",
        source_type="web",
        title="不可用来源",
        status="unavailable",
        applicability="本轮不可用",
    )
    assert unavailable.adopted_text is None
    with pytest.raises(ValidationError, match="unavailable"):
        EvidenceRecord(
            evidence_id="E3",
            source_type="web",
            title="不可用来源",
            status="unavailable",
            locator="fake",
            adopted_text="不得存在",
            applicability="本轮不可用",
        )


def test_evolution_signal_rejects_content_fields() -> None:
    signal = EvolutionSignal(
        run_fingerprint="a" * 64,
        route="quick",
        terminal_status="completed",
        risk_level="low",
        input_tokens=10,
        output_tokens=20,
        duration_ms=30,
        occurred_at=datetime.now(UTC),
    )
    assert signal.feedback_value == 0

    with pytest.raises(ValidationError):
        EvolutionSignal(
            **signal.model_dump(),
            user_text="不得记录",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        EvolutionSignal(
            **{
                **signal.model_dump(),
                "capability_ids": ("患者张三手机号13800138000",),
            }
        )
    with pytest.raises(ValidationError):
        EvolutionSignal(
            **{
                **signal.model_dump(),
                "skill_ids": ("a" * 1_000,),
            }
        )
    with pytest.raises(ValidationError):
        EvolutionSignal(
            **{
                **signal.model_dump(),
                "error_code": "患者胸痛",
            }
        )


def test_streaming_primitives_preserve_existing_behavior() -> None:
    canonical = CanonicalTextStream()
    assert canonical.feed("  第一段 ") == "第一段"
    assert canonical.feed(" 第二段  ") == "  第二段"
    canonical.finish()
    assert canonical.pending_whitespace == ""

    sentence_buffer = SafeSentenceBuffer(lambda: False)
    assert sentence_buffer.feed("这是待核验信息。")
    assert sentence_buffer.finish() == ""
