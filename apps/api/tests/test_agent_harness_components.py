"""Independent construction tests for Agent Harness component boundaries."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.agent_harness import HarnessComponents, ResolvedHarnessConfig
from gerclaw_api.modules.agent_harness import planning as planning_module
from gerclaw_api.modules.agent_harness.clinical_state import (
    ClinicalFact,
    ClinicalState,
    DeterministicClinicalStateReducer,
    FactProvenance,
    UserMessageClinicalProjector,
)
from gerclaw_api.modules.agent_harness.evidence import EvidenceRecord
from gerclaw_api.modules.agent_harness.evolution_signals import EvolutionSignal
from gerclaw_api.modules.agent_harness.planning import DynamicPlan, PlanNode
from gerclaw_api.modules.agent_harness.planning.agent_factory import (
    HIGH_VALUE_COMPRESSION_PROMPT,
    HIGH_VALUE_SUMMARY_SCHEMA,
    ProductionAgentFactory,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import PluginManifest
from gerclaw_api.modules.agent_harness.routing import (
    DeterministicRouter,
    RouteDecision,
    RouteKind,
    RoutingInput,
    RoutingPolicy,
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
    "evolution_governance",
    "evolution_signals",
)


def test_every_component_has_agent_instructions_and_reader_documentation() -> None:
    root = Path(__file__).parents[1] / "src" / "gerclaw_api" / "modules" / "agent_harness"

    for component in _COMPONENTS:
        assert (root / component / "AGENTS.md").is_file()
        assert (root / component / "README.md").is_file()


def test_root_harness_is_a_small_compatibility_facade() -> None:
    root = Path(__file__).parents[1] / "src" / "gerclaw_api" / "modules" / "agent_harness"
    facade = (root / "harness.py").read_text(encoding="utf-8")

    assert len(facade.splitlines()) <= 100
    for concrete_owner in (
        "FailoverChatModel",
        "HybridRAGModule",
        "ProductionMemoryModule",
        "GovernedToolRegistry",
    ):
        assert concrete_owner not in facade


def test_run_lifecycle_depends_only_on_protocol_safe_boundaries() -> None:
    root = Path(__file__).parents[1] / "src" / "gerclaw_api" / "modules" / "agent_harness"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (root / "run_lifecycle").glob("*.py")
    )

    for forbidden_owner in (
        "gerclaw_api.modules.memory",
        "gerclaw_api.modules.rag",
        "gerclaw_api.modules.search",
        "gerclaw_api.modules.runtime",
        "gerclaw_api.modules.skill",
        "gerclaw_api.modules.workflows",
    ):
        assert forbidden_owner not in source


def test_composition_entry_is_bounded_after_component_extraction() -> None:
    root = Path(__file__).parents[1] / "src" / "gerclaw_api" / "modules" / "agent_harness"
    orchestrator = (root / "orchestrator.py").read_text(encoding="utf-8")
    composition_setup = (root / "composition_setup.py").read_text(encoding="utf-8")

    assert len(orchestrator.splitlines()) <= 800
    assert len(composition_setup.splitlines()) <= 300
    assert "self._components.run_lifecycle" in composition_setup
    assert "self._components.context_snapshot_assembler" in composition_setup


def test_component_packages_do_not_read_environment_directly() -> None:
    root = Path(__file__).parents[1] / "src" / "gerclaw_api" / "modules" / "agent_harness"

    for component in _COMPONENTS:
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in (root / component).glob("*.py")
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


def test_deterministic_router_covers_quick_standard_deep_and_emergency() -> None:
    router = DeterministicRouter(
        RoutingPolicy(
            quick_max_characters=80,
            deep_min_characters=1_000,
            deep_attachment_count=2,
            deep_capability_count=2,
        )
    )

    assert router.decide(RoutingInput(message="1 + 1 = ?")).route is RouteKind.QUICK
    assert (
        router.decide(RoutingInput(message="老人最近头晕", medical_content=True)).route
        is RouteKind.STANDARD
    )
    assert (
        router.decide(
            RoutingInput(
                message="请综合评估并生成报告",
                medical_content=True,
            )
        ).route
        is RouteKind.DEEP
    )
    assert (
        router.decide(
            RoutingInput(
                message="请使用能力",
                selected_capabilities=("gerclaw.cga", "gerclaw.medication_review"),
            )
        ).route
        is RouteKind.DEEP
    )
    emergency = router.decide(
        RoutingInput(
            message="您好",
            selected_capabilities=("gerclaw.cga", "gerclaw.medication_review"),
            high_risk_detected=True,
        )
    )
    assert emergency.route is RouteKind.EMERGENCY
    assert emergency.model_allowed is False


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
    assert config.context_trigger_ratio < config.context_hard_stop_ratio
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
    with pytest.raises(ValidationError, match="soft trigger < hard stop"):
        ResolvedHarnessConfig(
            max_react_iterations=6,
            max_output_characters=20_000,
            max_output_bytes=80_000,
            evidence_top_k=8,
            memory_top_k=5,
            memory_min_score=0.6,
            approval_ttl_seconds=900,
            context_trigger_ratio=0.85,
            context_hard_stop_ratio=0.8,
            context_reserve_ratio=0.2,
        )


def test_agent_factory_uses_high_value_soft_threshold_compression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(planning_module.agent_factory, "Agent", capture_agent)
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
    factory = ProductionAgentFactory(
        model=object(),  # type: ignore[arg-type]
        config=config,
        workflow="chat",
    )

    factory.build(
        session_id="session-compression",
        state_context=[],
        toolkit=object(),  # type: ignore[arg-type]
        rag_middleware=object(),  # type: ignore[arg-type]
        memory_middleware=object(),  # type: ignore[arg-type]
        high_risk=False,
        document_focused=False,
        retrieval_disabled=False,
    )

    context_config = captured["context_config"]
    assert context_config.trigger_ratio == 0.85  # type: ignore[union-attr]
    assert context_config.reserve_ratio == 0.2  # type: ignore[union-attr]
    assert context_config.compression_prompt == HIGH_VALUE_COMPRESSION_PROMPT  # type: ignore[union-attr]
    assert context_config.summary_schema == HIGH_VALUE_SUMMARY_SCHEMA  # type: ignore[union-attr]
    for field in ("user_requirements", "clinical_facts", "unresolved_items", "source_references"):
        assert field in context_config.summary_schema["required"]  # type: ignore[union-attr]


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
    with pytest.raises(ValidationError, match="trusted-tool"):
        ClinicalFact(
            fact_id="symptom-2",
            category="symptom",
            value="头晕",
            status="confirmed",
            provenance=(provenance,),
        )
    with pytest.raises(ValidationError, match="bounded"):
        ClinicalFact(
            fact_id="symptom-3",
            category="symptom",
            value="a" * 5_001,
            status="reported",
            provenance=(provenance,),
        )
    with pytest.raises(ValidationError):
        ClinicalState(unknowns=("a" * 5_001,))


def test_clinical_state_reducer_merges_equal_observations_with_provenance() -> None:
    observed_at = datetime.now(UTC)
    user_provenance = FactProvenance(
        source_type="user",
        source_id="message-1",
        observed_at=observed_at,
    )
    tool_provenance = FactProvenance(
        source_type="trusted_tool",
        source_id="observation-1",
        observed_at=observed_at,
    )
    reducer = DeterministicClinicalStateReducer()
    current = ClinicalState(
        facts=(
            ClinicalFact(
                fact_id="blood-pressure",
                category="observation",
                value={"systolic": 150, "diastolic": 90, "unit": "mmHg"},
                status="reported",
                provenance=(user_provenance,),
            ),
        ),
        unknowns=("blood-pressure", "持续时间"),
    )

    reduced = reducer.reduce(
        current,
        (
            ClinicalFact(
                fact_id="blood-pressure",
                category="observation",
                value={"systolic": 150, "diastolic": 90, "unit": "mmHg"},
                status="confirmed",
                provenance=(tool_provenance,),
            ),
        ),
    )

    assert len(reduced.facts) == 1
    assert reduced.facts[0].status == "confirmed"
    assert reduced.facts[0].provenance == (user_provenance, tool_provenance)
    assert reduced.unknowns == ("持续时间",)
    assert reduced.conflicts == ()


def test_clinical_state_reducer_preserves_conflicting_candidates_and_unknowns() -> None:
    observed_at = datetime.now(UTC)
    user_provenance = FactProvenance(
        source_type="user",
        source_id="message-1",
        observed_at=observed_at,
    )
    tool_provenance = FactProvenance(
        source_type="trusted_tool",
        source_id="medication-list-1",
        observed_at=observed_at,
    )
    reducer = DeterministicClinicalStateReducer()
    current = ClinicalState(
        facts=(
            ClinicalFact(
                fact_id="current-aspirin-dose",
                category="medication",
                value="每日 100 mg",
                status="reported",
                provenance=(user_provenance,),
            ),
        ),
        unknowns=("过敏史",),
    )

    reduced = reducer.reduce(
        current,
        (
            ClinicalFact(
                fact_id="current-aspirin-dose",
                category="medication",
                value="每日 50 mg",
                status="confirmed",
                provenance=(tool_provenance,),
            ),
        ),
        unknowns=("近期出血", "过敏史"),
    )
    repeated = reducer.reduce(reduced, reduced.facts)

    assert [fact.value for fact in reduced.facts] == ["每日 100 mg", "每日 50 mg"]
    assert {fact.status for fact in reduced.facts} == {"conflicted"}
    assert reduced.conflicts == ("current-aspirin-dose",)
    assert reduced.unknowns == ("过敏史", "近期出血")
    assert repeated == reduced
    assert all(fact.category != "negative_evidence" for fact in reduced.facts)


def test_clinical_state_reducer_resolves_only_explicit_unknown_labels() -> None:
    reducer = DeterministicClinicalStateReducer()
    reduced = reducer.reduce(
        ClinicalState(unknowns=("持续时间", "是否跌倒")),
        (),
        resolved_unknowns=("持续时间",),
    )

    assert reduced.unknowns == ("是否跌倒",)
    assert reduced.facts == ()


def test_user_message_projector_is_idempotent_and_records_red_flags() -> None:
    projector = UserMessageClinicalProjector(DeterministicClinicalStateReducer())
    message_id = uuid.uuid4()
    observed_at = datetime.now(UTC)

    state = projector.project(
        ClinicalState(unknowns=("当前用药",)),
        message_id=message_id,
        message="老人突然胸痛",
        observed_at=observed_at,
        red_flag_codes=("chest_pain",),
    )
    replayed = projector.project(
        state,
        message_id=message_id,
        message="老人突然胸痛",
        observed_at=datetime.now(UTC),
        red_flag_codes=("chest_pain",),
    )

    assert replayed == state
    assert state.unknowns == ("当前用药",)
    assert [fact.category for fact in state.facts] == [
        "chief_complaint",
        "symptom",
        "red_flag",
    ]
    assert all(fact.status == "reported" for fact in state.facts)
    assert all(fact.provenance[0].source_id == f"message:{message_id}" for fact in state.facts)


def test_user_message_projector_extracts_only_explicit_structured_facts() -> None:
    projector = UserMessageClinicalProjector(DeterministicClinicalStateReducer())

    state = projector.project(
        ClinicalState(),
        message_id=uuid.uuid4(),
        message=(
            "老人78岁, 有高血压病史, 正在服用氨氯地平5mg每日一次, 没有药物过敏, 最近头晕持续3天。"
        ),
        observed_at=datetime.now(UTC),
        red_flag_codes=(),
    )

    categories = {fact.category for fact in state.facts}
    assert {
        "chief_complaint",
        "demographic",
        "negative_evidence",
        "medication",
        "symptom",
        "history",
        "timeline",
    } <= categories
    assert all(fact.status == "reported" for fact in state.facts)
    assert all(
        provenance.source_type == "user" for fact in state.facts for provenance in fact.provenance
    )


@pytest.mark.parametrize(
    ("first_message", "second_message", "fact_id"),
    [
        ("老人70岁。", "老人实际71岁。", "demographic:age_years"),
        ("没有药物过敏。", "对青霉素过敏。", "allergy:drug_status"),
        (
            "正在服用阿司匹林100mg每日一次。",
            "目前服用阿司匹林50mg每日一次。",
            "medication:current_list",
        ),
    ],
)
def test_user_message_projector_marks_singleton_fact_changes_as_conflicts(
    first_message: str,
    second_message: str,
    fact_id: str,
) -> None:
    projector = UserMessageClinicalProjector(DeterministicClinicalStateReducer())
    first_message_id = uuid.uuid4()
    second_message_id = uuid.uuid4()

    first = projector.project(
        ClinicalState(),
        message_id=first_message_id,
        message=first_message,
        observed_at=datetime.now(UTC),
        red_flag_codes=(),
    )
    conflicted = projector.project(
        first,
        message_id=second_message_id,
        message=second_message,
        observed_at=datetime.now(UTC),
        red_flag_codes=(),
    )
    replayed = projector.project(
        conflicted,
        message_id=second_message_id,
        message=second_message,
        observed_at=datetime.now(UTC),
        red_flag_codes=(),
    )

    singleton_facts = [fact for fact in conflicted.facts if fact.fact_id == fact_id]
    assert len(singleton_facts) == 2
    assert all(fact.status == "conflicted" for fact in singleton_facts)
    assert conflicted.conflicts == (fact_id,)
    assert replayed == conflicted


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
        run_status="completed",
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

    sentence_buffer = SafeSentenceBuffer(lambda _segment: False)
    assert sentence_buffer.feed("这是待核验信息。")
    assert sentence_buffer.finish() == ""
