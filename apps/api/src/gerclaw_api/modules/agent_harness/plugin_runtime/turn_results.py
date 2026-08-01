"""One-turn reuse coordinator for authorized inputs and local evidence."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import cast

from gerclaw_api.modules.agent_harness.clinical_state import ClinicalState
from gerclaw_api.modules.agent_harness.context_snapshot.uploaded_input import (
    UploadedInputProjector,
)
from gerclaw_api.modules.agent_harness.plugin_runtime.shared_results import (
    SharedResultKind,
    SharedResultRef,
    SharedResultScope,
    TurnSharedResultStore,
)
from gerclaw_api.modules.rag.protocols import RetrievalResult
from gerclaw_api.security import JsonValue

EventEmitter = Callable[[str, dict[str, JsonValue]], Awaitable[None]]
EvidenceRetriever = Callable[[], Awaitable[list[RetrievalResult]]]


class TurnResultReuse:
    """Compute each reusable turn input once behind an exact private scope."""

    def __init__(
        self,
        *,
        scope: SharedResultScope,
        clinical_state: ClinicalState,
        uploaded_input: UploadedInputProjector,
    ) -> None:
        self._scope = scope
        self._store = TurnSharedResultStore(scope)
        self._clinical_state = clinical_state
        self._uploaded_input = uploaded_input
        self._clinical_ref: SharedResultRef | None = None
        self._attachment_ref: SharedResultRef | None = None
        self._evidence_ref: SharedResultRef | None = None

    async def clinical_state(self) -> ClinicalState:
        async def provide() -> ClinicalState:
            return self._clinical_state

        result = await self._store.get_or_create(
            key="clinical_state",
            kind=SharedResultKind.CLINICAL_OBSERVATION,
            producer="clinical_state.reducer",
            reusable_by=("planning", "answer.compose", "report.compose"),
            factory=provide,
        )
        self._clinical_ref = result.reference
        return cast(
            ClinicalState,
            self._store.resolve(
                result.reference,
                scope=self._scope,
                consumer="planning",
            ),
        )

    async def attachment_projector(self) -> UploadedInputProjector:
        async def provide() -> UploadedInputProjector:
            return self._uploaded_input

        result = await self._store.get_or_create(
            key="attachment_projection",
            kind=SharedResultKind.ATTACHMENT_PROJECTION,
            producer="attachment.inspect",
            reusable_by=("planning", "answer.compose", "report.compose"),
            factory=provide,
        )
        self._attachment_ref = result.reference
        return cast(
            UploadedInputProjector,
            self._store.resolve(
                result.reference,
                scope=self._scope,
                consumer="planning",
            ),
        )

    async def prefetch_local_evidence(
        self,
        *,
        call_id: str,
        retrieve: EvidenceRetriever,
        add_tool_call: Callable[[], None],
        emit: EventEmitter,
        tolerate_failure: bool,
    ) -> list[RetrievalResult]:
        """Emit one truthful terminal event and retain only real retrieval output."""

        started_at = time.monotonic()
        await emit(
            "tool_call",
            {
                "tool_call_id": call_id,
                "tool_name": "search_knowledge",
                "status": "running",
            },
        )

        async def provide() -> list[RetrievalResult]:
            add_tool_call()
            return await retrieve()

        try:
            result = await self._store.get_or_create(
                key="local_evidence",
                kind=SharedResultKind.LOCAL_EVIDENCE,
                producer="evidence.retrieve",
                reusable_by=("answer.compose", "report.compose"),
                factory=provide,
            )
        except Exception:
            await emit(
                "tool_result",
                {
                    "tool_call_id": call_id,
                    "tool_name": "search_knowledge",
                    "status": "failed",
                    "duration_ms": max(0, int((time.monotonic() - started_at) * 1_000)),
                    "result_summary": "本地医学证据暂时不可用",
                },
            )
            if tolerate_failure:
                return []
            raise
        self._evidence_ref = result.reference
        evidence = cast(
            list[RetrievalResult],
            self._store.resolve(
                result.reference,
                scope=self._scope,
                consumer="answer.compose",
            ),
        )
        await emit(
            "tool_result",
            {
                "tool_call_id": call_id,
                "tool_name": "search_knowledge",
                "status": "success",
                "duration_ms": max(0, int((time.monotonic() - started_at) * 1_000)),
                "result_count": len(evidence),
                "result_summary": f"已找到 {len(evidence)} 条相关医学证据",
            },
        )
        return evidence

    def evidence_for(self, consumer: str) -> list[RetrievalResult]:
        if self._evidence_ref is None:
            return []
        return cast(
            list[RetrievalResult],
            self._store.resolve(
                self._evidence_ref,
                scope=self._scope,
                consumer=consumer,
            ),
        )

    def public_kinds(self) -> list[JsonValue]:
        return [
            kind
            for kind, reference in (
                ("clinical_observation", self._clinical_ref),
                ("attachment_projection", self._attachment_ref),
                ("local_evidence", self._evidence_ref),
            )
            if reference is not None
        ]
