"""Governed clinical capability selection and request-local result reuse."""

from __future__ import annotations

import uuid
from typing import cast

import pytest

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.context_snapshot import UploadedInputProjector
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    CapabilityEntrypoint,
    CapabilityInvocationContext,
    CapabilityResult,
    CapabilitySelectionMode,
    GovernedCapabilityCatalog,
    GovernedCapabilityRuntime,
    PluginRuntimeError,
    SharedResultKind,
    SharedResultScope,
    TurnResultReuse,
    TurnSharedResultStore,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.turn_toolkit import (
    PrefetchedTurnRAGModule,
)
from gerclaw_api.modules.rag.protocols import IndexResult, RAGModule, RAGStatus, RetrievalResult
from gerclaw_api.security import JsonValue


def test_catalog_registers_existing_owners_without_copying_their_implementations() -> None:
    manifests = {item.capability_id: item for item in GovernedCapabilityCatalog().manifests()}

    assert {
        capability_id: (item.owner_module, item.entrypoint)
        for capability_id, item in manifests.items()
    } == {
        "gerclaw.cga": ("cga", CapabilityEntrypoint.CGA_ASSESSMENT),
        "gerclaw.medication_review": (
            "medication_review",
            CapabilityEntrypoint.MEDICATION_REVIEW_INTAKE,
        ),
        "gerclaw.five_prescription": (
            "prescription",
            CapabilityEntrypoint.FIVE_PRESCRIPTION_INTAKE,
        ),
        "gerclaw.report_artifact": (
            "run_artifact",
            CapabilityEntrypoint.RUN_ARTIFACT,
        ),
    }


def test_manual_workflow_and_automatic_selection_use_the_same_allowlist() -> None:
    catalog = GovernedCapabilityCatalog()

    selected = catalog.select(
        message="请做用药审查, 并整理成一份报告",
        workflow="standard",
        requested=("gerclaw.cga", "gerclaw.medication_review"),
    )
    cga, medication, report = selected.selected

    assert cga.source is CapabilitySelectionMode.MANUAL
    assert medication.source is CapabilitySelectionMode.MANUAL
    assert report.source is CapabilitySelectionMode.AUTOMATIC
    assert selected.ids == (
        "gerclaw.cga",
        "gerclaw.medication_review",
        "gerclaw.report_artifact",
    )

    workflow_selection = catalog.select(message="继续", workflow="cga")
    assert workflow_selection.ids == ("gerclaw.cga",)
    assert workflow_selection.selected[0].source is CapabilitySelectionMode.WORKFLOW


def test_catalog_fails_closed_for_unknown_or_unsupported_manual_capability() -> None:
    catalog = GovernedCapabilityCatalog()

    with pytest.raises(PluginRuntimeError, match="CAPABILITY_UNKNOWN"):
        catalog.select(
            message="执行未知能力",
            workflow="standard",
            requested=("gerclaw.unknown",),
        )
    with pytest.raises(PluginRuntimeError, match="CAPABILITY_WORKFLOW_UNSUPPORTED"):
        catalog.select(
            message="用药审查",
            workflow="companion",
            requested=("gerclaw.medication_review",),
        )


@pytest.mark.asyncio
async def test_runtime_dispatches_to_exact_owner_and_rejects_mismatched_result() -> None:
    calls: list[tuple[str, str]] = []

    async def cga_owner(
        context: CapabilityInvocationContext,
        capability_id: str,
    ) -> CapabilityResult:
        calls.append((capability_id, context.session_id))
        return CapabilityResult(
            capability_id=capability_id,
            result_ref="cga-workspace:session",
            public_summary="CGA 工作台已连接。",
        )

    runtime = GovernedCapabilityRuntime(
        catalog=GovernedCapabilityCatalog(),
        handlers={CapabilityEntrypoint.CGA_ASSESSMENT: cga_owner},
    )
    result = await runtime.invoke(
        "gerclaw.cga",
        {
            "tenant_id": "tenant-default",
            "actor_id": "usr_test",
            "session_id": str(uuid.uuid4()),
            "trace_id": "trace_capability_runtime_0001",
        },
    )

    assert result.capability_id == "gerclaw.cga"
    assert len(calls) == 1
    with pytest.raises(PluginRuntimeError, match="CAPABILITY_INPUT_INVALID"):
        await runtime.invoke(
            "gerclaw.cga",
            {
                "tenant_id": "tenant-default",
                "actor_id": "usr_test",
                "session_id": str(uuid.uuid4()),
                "trace_id": "trace_capability_runtime_0003",
                "untrusted_override": True,
            },
        )
    assert len(calls) == 1
    with pytest.raises(PluginRuntimeError, match="CAPABILITY_OWNER_UNAVAILABLE"):
        await runtime.invoke(
            "gerclaw.medication_review",
            {
                "tenant_id": "tenant-default",
                "actor_id": "usr_test",
                "session_id": str(uuid.uuid4()),
                "trace_id": "trace_capability_runtime_0002",
            },
        )


@pytest.mark.asyncio
async def test_runtime_executes_manifest_output_contract_and_rejects_schema_drift() -> None:
    manifest = GovernedCapabilityCatalog().resolve("gerclaw.cga")
    drifted = manifest.model_copy(
        update={"input_schema": {"type": "object", "additionalProperties": True}}
    )

    with pytest.raises(PluginRuntimeError, match="CAPABILITY_SCHEMA_UNSUPPORTED"):
        GovernedCapabilityRuntime(
            catalog=GovernedCapabilityCatalog((drifted,)),
            handlers={},
        )

    async def malformed_owner(
        _context: CapabilityInvocationContext,
        capability_id: str,
    ) -> CapabilityResult:
        return cast(
            CapabilityResult,
            {
                "capability_id": capability_id,
                "result_ref": "cga-workspace:session",
                "public_summary": "CGA 工作台已连接。",
                "private_payload": "must not cross owner boundary",
            },
        )

    runtime = GovernedCapabilityRuntime(
        catalog=GovernedCapabilityCatalog((manifest,)),
        handlers={CapabilityEntrypoint.CGA_ASSESSMENT: malformed_owner},
    )
    with pytest.raises(PluginRuntimeError, match="CAPABILITY_OUTPUT_INVALID"):
        await runtime.invoke(
            "gerclaw.cga",
            {
                "tenant_id": "tenant-default",
                "actor_id": "usr_test",
                "session_id": str(uuid.uuid4()),
                "trace_id": "trace_capability_runtime_0004",
            },
        )


@pytest.mark.asyncio
async def test_shared_result_is_computed_once_and_reused_only_inside_exact_scope() -> None:
    scope = SharedResultScope(
        tenant_id="tenant-default",
        actor_id="usr_test",
        session_id=str(uuid.uuid4()),
        trace_id="trace_shared_result_0001",
    )
    store = TurnSharedResultStore(scope)
    calls = 0

    async def retrieve() -> list[str]:
        nonlocal calls
        calls += 1
        return ["evidence-1"]

    first = await store.get_or_create(
        key="local-evidence",
        kind=SharedResultKind.LOCAL_EVIDENCE,
        producer="evidence.retrieve",
        reusable_by=("answer.compose", "report.compose"),
        factory=retrieve,
    )
    second = await store.get_or_create(
        key="local-evidence",
        kind=SharedResultKind.LOCAL_EVIDENCE,
        producer="evidence.retrieve",
        reusable_by=("answer.compose", "report.compose"),
        factory=retrieve,
    )

    assert calls == 1
    assert first.reused is False
    assert second.reused is True
    assert second.reference == first.reference
    assert (
        store.resolve(
            first.reference,
            scope=scope,
            consumer="report.compose",
        )
        is first.value
    )

    wrong_scope = scope.model_copy(update={"trace_id": "trace_shared_result_0002"})
    with pytest.raises(PluginRuntimeError, match="SHARED_RESULT_SCOPE_MISMATCH"):
        store.resolve(first.reference, scope=wrong_scope, consumer="answer.compose")
    with pytest.raises(PluginRuntimeError, match="SHARED_RESULT_CONSUMER_DENIED"):
        store.resolve(first.reference, scope=scope, consumer="gerclaw.unknown")


@pytest.mark.asyncio
async def test_shared_result_key_cannot_be_rebound_to_a_different_contract() -> None:
    scope = SharedResultScope(
        tenant_id="tenant-default",
        actor_id="usr_test",
        session_id=str(uuid.uuid4()),
        trace_id="trace_shared_result_0003",
    )
    store = TurnSharedResultStore(scope)

    async def project() -> str:
        return "one projection"

    await store.get_or_create(
        key="shared",
        kind=SharedResultKind.ATTACHMENT_PROJECTION,
        producer="attachment.inspect",
        reusable_by=("answer.compose",),
        factory=project,
    )
    with pytest.raises(PluginRuntimeError, match="SHARED_RESULT_KEY_CONTRACT_MISMATCH"):
        await store.get_or_create(
            key="shared",
            kind=SharedResultKind.LOCAL_EVIDENCE,
            producer="evidence.retrieve",
            reusable_by=("answer.compose",),
            factory=project,
        )


@pytest.mark.asyncio
async def test_prefetch_emits_exactly_one_success_terminal_and_reuses_result() -> None:
    scope = SharedResultScope(
        tenant_id="tenant-default",
        actor_id="usr_test",
        session_id=str(uuid.uuid4()),
        trace_id="trace_prefetch_0001",
    )
    reuse = TurnResultReuse(
        scope=scope,
        clinical_state=ClinicalState(),
        uploaded_input=UploadedInputProjector([], []),
    )
    events: list[tuple[str, dict[str, JsonValue]]] = []
    calls = 0

    async def retrieve() -> list[RetrievalResult]:
        nonlocal calls
        calls += 1
        return [
            RetrievalResult(
                content="可复用证据",
                source="guideline/source.md",
                score=0.8,
            )
        ]

    async def emit(kind: str, data: dict[str, JsonValue]) -> None:
        events.append((kind, data))

    result = await reuse.prefetch_local_evidence(
        call_id="rag-prefetch:test",
        retrieve=retrieve,
        add_tool_call=lambda: None,
        emit=emit,
        tolerate_failure=False,
    )

    assert calls == 1
    assert result is reuse.evidence_for("report.compose")
    assert [data["status"] for kind, data in events if kind == "tool_result"] == ["success"]


@pytest.mark.asyncio
async def test_tolerated_prefetch_failure_never_emits_a_false_success() -> None:
    reuse = TurnResultReuse(
        scope=SharedResultScope(
            tenant_id="tenant-default",
            actor_id="usr_test",
            session_id=str(uuid.uuid4()),
            trace_id="trace_prefetch_0002",
        ),
        clinical_state=ClinicalState(),
        uploaded_input=UploadedInputProjector([], []),
    )
    events: list[tuple[str, dict[str, JsonValue]]] = []

    async def unavailable() -> list[RetrievalResult]:
        raise RuntimeError("local index unavailable")

    async def emit(kind: str, data: dict[str, JsonValue]) -> None:
        events.append((kind, data))

    assert (
        await reuse.prefetch_local_evidence(
            call_id="rag-prefetch:test",
            retrieve=unavailable,
            add_tool_call=lambda: None,
            emit=emit,
            tolerate_failure=True,
        )
        == []
    )
    assert [data["status"] for kind, data in events if kind == "tool_result"] == ["failed"]


@pytest.mark.asyncio
async def test_agentic_rag_reuses_prefetched_user_query_results_without_retrieval_drift() -> None:
    class _RAGDelegate:
        def __init__(self) -> None:
            self.retrieve_calls = 0

        async def retrieve(
            self,
            query: str,
            top_k: int = 5,
            filters: object | None = None,
        ) -> list[RetrievalResult]:
            del query, top_k, filters
            self.retrieve_calls += 1
            return [
                RetrievalResult(
                    content="模型漂移查询得到的不相关证据",
                    source="unrelated.md",
                    score=0.99,
                )
            ]

        async def index_document(self, file_path: str, doc_type: str) -> IndexResult:
            del file_path, doc_type
            raise AssertionError("indexing is not part of a chat turn")

        async def status(self) -> RAGStatus:
            raise AssertionError("status is not part of a chat turn")

    delegate = _RAGDelegate()
    prefetched = [
        RetrievalResult(
            content="用户原始问题对应的用药核对证据",
            source="medication-reconciliation.md",
            score=0.8,
        )
    ]
    turn_module = PrefetchedTurnRAGModule(
        delegate=cast(RAGModule, delegate),
        results=prefetched,
    )

    repeated = await turn_module.retrieve("模型后来改写成了衰弱筛查", top_k=5)

    assert repeated == prefetched
    assert delegate.retrieve_calls == 0
