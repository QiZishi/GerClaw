"""Production composition entry for one modular Agent Harness turn."""

# ruff: noqa: RUF001
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from functools import partial

from gerclaw_api.modules.agent_harness.composition_setup import (
    ProductionHarnessCompositionSetup,
)
from gerclaw_api.modules.agent_harness.context_snapshot import (
    ContextSnapshotError,
    ContextSnapshotInputs,
    build_agent_state_context,
    compose_context_snapshot,
    render_untrusted_clinical_state,
)
from gerclaw_api.modules.agent_harness.evidence import (
    BoundTurnEvidence,
    ModelCitationBindingScope,
    bind_turn_evidence,
    prune_unbound_clinical_claims,
    resolve_referential_evidence_query,
)
from gerclaw_api.modules.agent_harness.orchestration_support import (
    OrchestrationSupportMixin,
    classify_answer_step_failure,
)
from gerclaw_api.modules.agent_harness.planning import (
    ClinicalDecisionCoordinator,
    PlanExecutionSnapshot,
    PlanNodeStatus,
    TurnExecutionGovernance,
    answer_presentation_contract,
    emit_deterministic_clarification,
)
from gerclaw_api.modules.agent_harness.plugin_runtime import (
    CapabilityResult,
    SharedResultScope,
    TurnResultReuse,
    bind_allowed_tool_preflight,
    build_turn_toolkit,
)
from gerclaw_api.modules.agent_harness.protocols import (
    AgentContext,
    StreamEvent,
)
from gerclaw_api.modules.agent_harness.routing import RouteKind
from gerclaw_api.modules.agent_harness.run_lifecycle import (
    CanonicalTextStream,
    EmptyAgentResponseError,
    RepairableAgentSession,
    SafeSentenceBuffer,
    UnboundClinicalClaimsError,
    UnsupportedAgentContextError,
    project_with_output_protocol_repair,
    validate_terminal_response_candidate,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.agent_stream import (
    AgentStreamResult,
    final_agent_text,
)
from gerclaw_api.modules.agent_harness.run_lifecycle.directive_runtime import (
    RuntimeDirectiveEmergency,
)
from gerclaw_api.modules.agent_harness.safety import (
    HIGH_RISK_NOTICE,
    MEDICAL_DISCLAIMER,
    PATIENT_CLINICAL_RISK_NOTICE,
    build_evidence_context,
    citations_from_results,
    detect_high_risk,
    is_medical_message,
    requires_clinical_evidence,
    requires_patient_clinical_risk_notice,
    safety_decision,
)
from gerclaw_api.modules.companion.policy import is_companion_workflow
from gerclaw_api.modules.contracts import AgentResponse, Citation
from gerclaw_api.modules.rag import capture_agentic_rag_results
from gerclaw_api.modules.runtime.budget import (
    RuntimeBudgetExceededError,
    RuntimeBudgetTracker,
)
from gerclaw_api.modules.runtime.models import (
    ActorRole,
)
from gerclaw_api.modules.search import (
    capture_agent_search_results,
    capture_search_attempts,
    citations_from_search_results,
)
from gerclaw_api.security import JsonValue
from gerclaw_api.services.model_router import capture_model_attempts

StreamCallback = Callable[[StreamEvent], Awaitable[None] | None]
CapabilityResultObserver = Callable[
    [PlanExecutionSnapshot, CapabilityResult],
    Awaitable[None],
]
_EVIDENCE_UNAVAILABLE_CLARIFICATION = (
    "目前缺少可核验的资料，暂不适合据此作个体化判断。"
    "请补充症状出现和变化、近期检查或完整用药信息，我可以结合这些资料继续说明。"
)
_SafeSentenceBuffer = SafeSentenceBuffer
_CanonicalTextStream = CanonicalTextStream
_final_agent_text = final_agent_text


def _not_clinical(_segment: str) -> bool:
    return False


class ProductionAgentHarness(ProductionHarnessCompositionSetup, OrchestrationSupportMixin):
    """One-turn isolated harness over shared model and retrieval clients."""

    async def assemble_context(
        self,
        session_id: str,
        user_id: str,
        loaded_skills: list[str],
        uploaded_files: list[str],
    ) -> AgentContext:
        """Assemble validated short- and long-term context for one isolated turn."""
        if str(self._execution.session_id) != session_id or self._execution.actor_id != user_id:
            raise ContextSnapshotError("execution identity does not match requested Agent context")
        if loaded_skills != self._loaded_skill_ids:
            raise UnsupportedAgentContextError("validated Skill context does not match the request")
        expected_document_ids = [str(item.document_id) for item in self._uploaded_documents]
        if uploaded_files != expected_document_ids:
            raise UnsupportedAgentContextError(
                "validated uploaded-document context does not match the request"
            )
        companion = is_companion_workflow(self._workflow)
        quick_route = (
            self._route_decision is not None and self._route_decision.route is RouteKind.QUICK
        )
        return compose_context_snapshot(
            self._context_assembler,
            ContextSnapshotInputs(
                execution=self._execution,
                history=tuple(self._history),
                profile_context=self._profile_context,
                profile_version=self._profile_version,
                memory_refs=tuple(self._memory_refs),
                session_summary=self._session_summary,
                clinical_state=self._clinical_state,
                loaded_skills=tuple(loaded_skills),
                uploaded_files=tuple(uploaded_files),
                companion=companion,
                quick_route=quick_route,
                search_available=self._search_module is not None and self._search_enabled,
                skill_available=bool(self._agent_skills),
                preassembled=self._preassembled_context,
            ),
        )

    async def process_message(
        self,
        user_message: str,
        session_id: str,
        context: AgentContext,
        stream_callback: StreamCallback,
    ) -> AgentResponse:
        """Run preflight evidence, AgentScope ReAct, and deterministic safety."""
        budget = RuntimeBudgetTracker(self._execution_budget)
        turn_results = TurnResultReuse(
            scope=SharedResultScope(
                tenant_id=self._execution.tenant_id,
                actor_id=self._execution.actor_id,
                session_id=str(self._execution.session_id),
                trace_id=self._execution.trace_id,
            ),
            clinical_state=context.clinical_state,
            uploaded_input=self._uploaded_input,
        )
        turn_clinical_state = await turn_results.clinical_state()
        await self._emit(
            stream_callback,
            "agent_start",
            {
                "agent": (
                    "gerclaw_emotional_companion"
                    if is_companion_workflow(self._workflow)
                    else "gerclaw_geriatric_specialist"
                ),
                "status": "running",
            },
        )
        companion = is_companion_workflow(self._workflow)
        medical_content = is_medical_message(user_message) and not companion
        clinical_claim_detector = requires_clinical_evidence if medical_content else _not_clinical
        high_risk_codes = detect_high_risk(user_message)
        clinical_decision = self._clinical_decision or ClinicalDecisionCoordinator(
            minimum_score=self._config.savi_minimum_score
        ).prepare(
            state=turn_clinical_state,
            message=user_message,
            has_attachments=bool(self._uploaded_documents or self._uploaded_images),
        )
        selected = clinical_decision.action_selection.selected
        prepared_turn = self._turn_planning.prepare(
            message=user_message,
            medical_content=medical_content,
            image_count=len(self._uploaded_images),
            document_count=len(self._uploaded_documents),
            capabilities=tuple([*self._loaded_skill_ids, *self._governed_capability_ids]),
            high_risk_detected=bool(high_risk_codes),
            selected_action=(selected.candidate.kind.value if selected is not None else "answer"),
        )
        route_decision = prepared_turn.route_decision
        dynamic_plan = prepared_turn.dynamic_plan
        governance = TurnExecutionGovernance(
            plan=dynamic_plan,
            decision=clinical_decision,
            execution_snapshot=self._plan_execution_snapshot,
            observer=self._plan_execution_observer,
        )
        # A pure request to summarize/read an attachment should not fabricate
        # unrelated medical context.  Once the user asks for a medical
        # interpretation (for example a blood-pressure or medication report),
        # the attachment is one evidence source alongside the normal governed
        # RAG/search path rather than a reason to disable it.
        document_focused = (
            not companion
            and not medical_content
            and self._uploaded_input.is_document_focused_request(user_message)
        )
        should_prefetch_local_evidence = medical_content and not document_focused and not companion
        has_uploaded_evidence = bool(self._uploaded_documents or self._uploaded_images)
        can_search_for_evidence = (
            self._search_module is not None and self._search_enabled and not document_focused
        )
        safe_high_risk_codes: list[JsonValue] = list(high_risk_codes)
        if route_decision.route is RouteKind.EMERGENCY:
            if governance.status_for("safety.emergency") is not PlanNodeStatus.COMPLETED:
                emergency_node = await governance.checkpoint_persisted("safety.emergency")
                await governance.complete_persisted(emergency_node)
            return await emit_deterministic_clarification(
                body=HIGH_RISK_NOTICE,
                high_risk_codes=high_risk_codes,
                emit=lambda kind, data: self._emit(stream_callback, kind, data),
                budget=budget,
                structured={
                    "loaded_skill_ids": list(context.loaded_skills),
                    "governed_capability_ids": list(self._governed_capability_ids),
                    "emergency_short_circuit": True,
                    "route": route_decision.route.value,
                    "route_reason": route_decision.reason_code,
                    "plan_node_ids": [node.node_id for node in dynamic_plan.nodes],
                    **(await governance.finish_persisted()),
                },
                emergency_short_circuit=True,
            )
        if governance.should_ask:
            if governance.status_for("clinical.ask") is not PlanNodeStatus.COMPLETED:
                ask_node = await governance.checkpoint_persisted("clinical.ask")
                await governance.complete_persisted(ask_node)
            return await emit_deterministic_clarification(
                body=governance.clarification_text(),
                high_risk_codes=high_risk_codes,
                emit=lambda kind, data: self._emit(stream_callback, kind, data),
                budget=budget,
                structured={
                    "response_kind": "clinical_clarification",
                    "route": route_decision.route.value,
                    "route_reason": route_decision.reason_code,
                    "plan_node_ids": [node.node_id for node in dynamic_plan.nodes],
                    **(await governance.finish_persisted()),
                },
                clinical_clarification=True,
            )
        attachment_projector = self._uploaded_input
        if self._uploaded_documents or self._uploaded_images:
            if governance.status_for("attachment.inspect") is PlanNodeStatus.COMPLETED:
                attachment_projector = await turn_results.attachment_projector()
            else:
                attachment_node = await governance.checkpoint_persisted("attachment.inspect")
                try:
                    attachment_projector = await turn_results.attachment_projector()
                except Exception:
                    await governance.fail_persisted(
                        attachment_node,
                        "ATTACHMENT_INSPECTION_FAILED",
                    )
                    raise
                await governance.complete_persisted(attachment_node)

        evidence_results = []
        if should_prefetch_local_evidence:
            evidence_query = resolve_referential_evidence_query(
                user_message,
                context,
                is_medical_message=is_medical_message,
            )
            evidence_node = await governance.checkpoint_persisted("evidence.retrieve")
            await self._emit(
                stream_callback,
                "reasoning_summary",
                {"content": "正在检索本地医学证据…", "status": "running"},
            )
            # The mandatory initial retrieval happens before AgentScope calls the
            # model, so it cannot be inferred from an AgentScope tool event.
            # Project the *same* operation as search_knowledge for the UI and
            # trace: users must be able to see evidence work actually occurring,
            # and no second retrieval or provider call is introduced here.
            prefetch_call_id = f"rag-prefetch:{self._execution.trace_id}"
            try:
                evidence_results = await turn_results.prefetch_local_evidence(
                    call_id=prefetch_call_id,
                    retrieve=lambda: self._rag_module.retrieve(
                        evidence_query,
                        top_k=self._config.evidence_top_k,
                    ),
                    add_tool_call=budget.add_tool_call,
                    emit=lambda kind, data: self._emit(stream_callback, kind, data),
                    # Uploads and governed web search are independent evidence
                    # sources. With neither available, retain fail-closed behavior.
                    tolerate_failure=has_uploaded_evidence or can_search_for_evidence,
                )
            except Exception:
                await governance.fail_persisted(
                    evidence_node,
                    "EVIDENCE_RETRIEVAL_FAILED",
                )
                raise
            await governance.complete_persisted(evidence_node)
        for capability_id in self._completed_capability_ids:
            await governance.complete_optional_capability_persisted(capability_id)
        completed_capability_ids = {item.capability_id for item in self._capability_results}
        planned_capabilities = {node.capability for node in dynamic_plan.nodes}
        for capability_id in self._governed_capability_ids:
            if (
                capability_id in completed_capability_ids
                or capability_id not in planned_capabilities
            ):
                continue
            capability_node = await governance.checkpoint_persisted(capability_id)
            if self._capability_invoker is None:
                await governance.fail_persisted(
                    capability_node,
                    "CAPABILITY_OWNER_UNAVAILABLE",
                )
                if "OPTIONAL_CAPABILITY_FAILED" not in self._warning_codes:
                    self._warning_codes.append("OPTIONAL_CAPABILITY_FAILED")
                continue
            try:
                capability_result = await self._capability_invoker(capability_id)
            except Exception:
                await governance.fail_persisted(
                    capability_node,
                    "CAPABILITY_OWNER_FAILED",
                )
                if "OPTIONAL_CAPABILITY_FAILED" not in self._warning_codes:
                    self._warning_codes.append("OPTIONAL_CAPABILITY_FAILED")
                continue
            if capability_result.capability_id != capability_id:
                await governance.fail_persisted(
                    capability_node,
                    "CAPABILITY_RESULT_MISMATCH",
                )
                if "OPTIONAL_CAPABILITY_FAILED" not in self._warning_codes:
                    self._warning_codes.append("OPTIONAL_CAPABILITY_FAILED")
                continue
            if self._capability_result_observer is not None:
                governance.complete(capability_node)
                await self._capability_result_observer(
                    governance.snapshot(),
                    capability_result,
                )
            else:
                await governance.complete_persisted(capability_node)
            self._capability_results.append(capability_result)
            completed_capability_ids.add(capability_id)
        initial_citations = citations_from_results(
            evidence_results,
            minimum_score=self._config.evidence_min_score,
            limit=self._config.evidence_top_k,
        )
        if (
            should_prefetch_local_evidence
            and not initial_citations
            and not has_uploaded_evidence
            and not can_search_for_evidence
        ):
            answer_node = await governance.checkpoint_persisted(governance.answer_capability())
            await governance.complete_persisted(answer_node)
            return await emit_deterministic_clarification(
                body=_EVIDENCE_UNAVAILABLE_CLARIFICATION,
                high_risk_codes=high_risk_codes,
                emit=lambda kind, data: self._emit(stream_callback, kind, data),
                budget=budget,
                structured={
                    "loaded_skill_ids": list(context.loaded_skills),
                    "governed_capability_ids": list(self._governed_capability_ids),
                    "capability_results": [
                        item.model_dump(mode="json") for item in self._capability_results
                    ],
                    "warning_codes": list(self._warning_codes),
                    "document_focused": False,
                    "evidence_state": "unavailable",
                    "route": route_decision.route.value,
                    "route_reason": route_decision.reason_code,
                    "plan_node_ids": [node.node_id for node in dynamic_plan.nodes],
                    **(await governance.finish_persisted()),
                },
                evidence_unavailable=True,
            )
        clinical_state_json, clinical_state_context = render_untrusted_clinical_state(
            turn_clinical_state
        )
        differential_json, differential_context = governance.differential_prompt_context()
        state_context = build_agent_state_context(
            context,
            clinical_state_context=clinical_state_context,
            differential_context=differential_context,
            uploaded_document_context=(
                attachment_projector.render_documents() if self._uploaded_documents else None
            ),
            local_evidence_context=(
                build_evidence_context(initial_citations) if initial_citations else None
            ),
            presentation_contract=answer_presentation_contract(user_message),
        )

        preflight = self._turn_planning.check_model(
            usage=budget.snapshot(),
            text_values=(
                user_message,
                context.profile_context,
                context.session_summary,
                clinical_state_json,
                differential_json,
                *(item.text for item in context.conversation_history),
                *(item.content for item in self._uploaded_documents),
                *(item.excerpt for item in initial_citations),
            ),
            image_count=len(self._uploaded_images),
        )
        if not preflight.allowed:
            raise RuntimeBudgetExceededError(preflight.reason_code)
        if self._memory_module is None:
            raise UnsupportedAgentContextError(
                "memory module is unavailable for a non-emergency route"
            )
        agent_session: RepairableAgentSession
        react_boundaries = self._react_boundaries.bind(
            agent_provider=lambda: agent_session.agent,
            budget=budget,
        )

        turn_toolkit = await build_turn_toolkit(
            config=self._config,
            rag_module=self._rag_module,
            memory_module=self._memory_module,
            search_module=self._search_module,
            search_enabled=self._search_enabled,
            actor_id=context.execution.actor_id,
            user_message=user_message,
            principal=self._runtime_principal,
            skills=self._agent_skills,
            registry_factory=self._tool_registry_factory,
            tools_disabled=(
                document_focused or companion or route_decision.route is RouteKind.QUICK
            ),
            prefetched_local_evidence=(
                evidence_results if should_prefetch_local_evidence else None
            ),
            tool_execution_preflight=bind_allowed_tool_preflight(
                boundary=react_boundaries,
                result_limit_tokens=self._config.tool_result_reserve_tokens,
            ),
        )
        result_reserve_by_tool = {
            name: min(
                self._config.tool_result_reserve_tokens,
                capability.max_output_bytes,
            )
            for name, capability in turn_toolkit.capabilities.items()
        }
        agent_session = RepairableAgentSession.from_factory(
            factory=self._agent_factory,
            base_context=state_context,
            configure_agent=lambda agent: react_boundaries.install_on_agent(
                agent,
                result_reserve_by_tool=result_reserve_by_tool,
            ),
            session_id=session_id,
            toolkit=turn_toolkit.toolkit,
            rag_middleware=turn_toolkit.rag_middleware,
            memory_middleware=turn_toolkit.memory_middleware,
            high_risk=bool(high_risk_codes),
            document_focused=document_focused,
            retrieval_disabled=route_decision.route is RouteKind.QUICK,
        )
        effective_user_message, directive_response = await self._prepare_initial_runtime_directives(
            agent=agent_session.agent,
            budget=budget,
            user_message=user_message,
            stream_callback=stream_callback,
        )
        if directive_response is not None:
            return directive_response
        answer_node = await governance.checkpoint_persisted(governance.answer_capability())

        skill_metadata = self._skill_metadata(self._agent_skills)
        output_contract_retries = 0
        pruned_claim_count = 0
        validated_evidence: BoundTurnEvidence | None = None
        with (
            capture_model_attempts() as attempts,
            capture_agentic_rag_results() as agentic_results,
            capture_agent_search_results() as search_results,
            capture_search_attempts() as search_attempts,
        ):
            citation_scope = ModelCitationBindingScope(
                local_citation_count=len(initial_citations),
                web_citation_count_provider=lambda: len(
                    citations_from_search_results(search_results)
                ),
                attachment_citation_count=(
                    len(attachment_projector.document_citations())
                    + len(attachment_projector.image_citations())
                ),
            )

            park_approvals = partial(
                self._persist_approval_requests,
                capabilities=turn_toolkit.capabilities,
                input_models=turn_toolkit.input_models,
                stream_callback=stream_callback,
            )
            observe_tool_result = self._skill_result_observer(governance)

            async def apply_directives_after_tool() -> int:
                return await self._runtime_directives.apply_after_tool(
                    agent=agent_session.agent,
                    budget=budget,
                )

            def candidate_evidence() -> tuple[list[Citation], list[Citation], list[Citation]]:
                candidate_local = citations_from_results(
                    turn_results.evidence_for(
                        "report.compose"
                        if governance.answer_capability() == "report.compose"
                        else "answer.compose"
                    )
                    + agentic_results,
                    minimum_score=self._config.evidence_min_score,
                    limit=self._config.evidence_top_k,
                )
                return (
                    candidate_local,
                    citations_from_search_results(search_results),
                    [
                        *attachment_projector.document_citations(),
                        *attachment_projector.image_citations(),
                    ],
                )

            def validate_candidate(result: AgentStreamResult) -> AgentStreamResult:
                nonlocal validated_evidence
                candidate_local, candidate_web, candidate_attachments = candidate_evidence()
                validated_evidence = validate_terminal_response_candidate(
                    result,
                    initial_local=initial_citations,
                    additional_local=candidate_local,
                    web=candidate_web,
                    attachments=candidate_attachments,
                    is_clinical_claim=clinical_claim_detector,
                    high_risk_codes=high_risk_codes,
                    medical_content=medical_content,
                    patient_facing=bool(
                        self._runtime_principal is not None
                        and self._runtime_principal.role in {ActorRole.GUEST, ActorRole.PATIENT}
                    ),
                )
                return replace(result, text=validated_evidence.text)

            def recover_repeated_claim_failure(
                result: AgentStreamResult,
                error: Exception,
            ) -> AgentStreamResult | None:
                nonlocal pruned_claim_count
                if not isinstance(error, UnboundClinicalClaimsError):
                    return None
                candidate_local, candidate_web, candidate_attachments = candidate_evidence()
                bound = bind_turn_evidence(
                    result.text,
                    initial_local=initial_citations,
                    additional_local=candidate_local,
                    web=candidate_web,
                    attachments=candidate_attachments,
                    is_clinical_claim=clinical_claim_detector,
                    markers_already_bound=True,
                )
                recovered_text, removed_count = prune_unbound_clinical_claims(
                    bound.text,
                    citations=list(bound.citations),
                    is_clinical_claim=clinical_claim_detector,
                )
                if removed_count == 0:
                    return None
                pruned_claim_count = removed_count
                if not recovered_text:
                    recovered_text = (
                        "现有资料不足以支持具体结论。"
                        "请补充相关资料或允许继续检索，我会据此继续回答。"
                    )
                return replace(result, text=recovered_text)

            try:
                stream_result, output_contract_retries = await project_with_output_protocol_repair(
                    session=agent_session,
                    publish=lambda kind, data: self._emit(stream_callback, kind, data),
                    budget=budget,
                    observer=self._attempt_repair_observer,
                    classify_failure=classify_answer_step_failure,
                    user_message=attachment_projector.user_message(effective_user_message),
                    wall_clock_seconds=self._execution_budget.wall_clock_seconds,
                    max_output_characters=self._config.max_output_characters,
                    park_approvals=park_approvals,
                    evidence_available=citation_scope.segment_has_evidence,
                    public_text_transform=citation_scope.normalize_public_text,
                    memory_guard=turn_toolkit.memory_guard,
                    skill_metadata=skill_metadata,
                    search_results=search_results,
                    lifecycle=self._run_lifecycle,
                    timeout_error_factory=lambda: RuntimeBudgetExceededError(
                        "RUNTIME_WALL_CLOCK_EXCEEDED"
                    ),
                    tool_result_observer=observe_tool_result,
                    safe_boundary_observer=apply_directives_after_tool,
                    validate_result=validate_candidate,
                    recover_repeated_failure=recover_repeated_claim_failure,
                )
            except RuntimeDirectiveEmergency as emergency:
                await governance.complete_persisted(answer_node)
                await governance.finish_persisted()
                return await self._emit_runtime_directive_emergency(
                    emergency.risk_codes,
                    budget=budget,
                    stream_callback=stream_callback,
                )
            except Exception:
                await governance.fail_persisted(
                    answer_node,
                    "ANSWER_EXECUTION_FAILED",
                )
                raise
            selected_model_preference = next(
                (item.preference for item in reversed(attempts) if item.outcome == "succeeded"),
                None,
            )

        model_text = stream_result.text
        if not model_text.strip():
            await governance.fail_persisted(
                answer_node,
                "ANSWER_OUTPUT_EMPTY",
            )
            raise EmptyAgentResponseError("model completed without public text")
        try:
            if validated_evidence is None:
                raise RuntimeError("terminal evidence was not validated")
            bound_evidence = validated_evidence
            model_text = bound_evidence.text
            citations = list(bound_evidence.citations)
            claim_audit = bound_evidence.claim_audit
            patient_clinical_risk_notice_applied = bool(
                self._runtime_principal is not None
                and self._runtime_principal.role in {ActorRole.GUEST, ActorRole.PATIENT}
                and requires_patient_clinical_risk_notice(model_text)
            )
            patient_risk_delta = (
                f"\n\n{PATIENT_CLINICAL_RISK_NOTICE}"
                if patient_clinical_risk_notice_applied
                else ""
            )
            disclaimer_delta = (
                f"{patient_risk_delta}\n\n{MEDICAL_DISCLAIMER}"
                if medical_content
                else patient_risk_delta
            )
            final_text = f"{model_text}{disclaimer_delta}"
            budget.check_wall_clock()
            if disclaimer_delta:
                budget.add_output(disclaimer_delta)
                await self._emit(
                    stream_callback,
                    "text_delta",
                    {"content": disclaimer_delta},
                )
        except Exception:
            await governance.fail_persisted(
                answer_node,
                "ANSWER_FINALIZATION_FAILED",
            )
            raise
        await governance.complete_persisted(answer_node)
        governance_result = await governance.finish_persisted()

        claims_complete = claim_audit.all_clinical_claims_bound
        safe_tool_names: list[JsonValue] = []
        response = AgentResponse(
            text=final_text,
            # Tool-produced evidence remains auditable even when a turn is not
            # classified as medical (for example an explicit English-language
            # WHO web search).  Hiding those citations would disconnect the
            # public answer from an external tool result already present in the
            # same trace.
            citations=citations,
            safety=safety_decision(
                high_risk_codes,
                medical_content=medical_content,
                deterministic_diagnosis_blocked=(stream_result.deterministic_diagnosis_blocked),
                evidence_backed_clinical_conclusion_allowed=(claims_complete),
                patient_clinical_risk_notice_applied=patient_clinical_risk_notice_applied,
            ),
            medical_content=medical_content,
            structured={
                "model_invoked": True,
                "model_preference": selected_model_preference,
                "model_attempt_count": sum(
                    1 for attempt in attempts if attempt.outcome == "started"
                ),
                "model_failures": sum(
                    1 for attempt in attempts if attempt.outcome in {"failed", "failed_partial"}
                ),
                "output_contract_retries": output_contract_retries,
                "pruned_unsupported_claim_count": pruned_claim_count,
                "input_tokens": stream_result.input_tokens,
                "output_tokens": stream_result.output_tokens,
                "tool_names": safe_tool_names,
                "high_risk_codes": safe_high_risk_codes,
                "search_attempts": [item.model_dump(mode="json") for item in search_attempts],
                "loaded_skill_ids": list(context.loaded_skills),
                "governed_capability_ids": list(self._governed_capability_ids),
                "capability_results": [
                    item.model_dump(mode="json") for item in self._capability_results
                ],
                "warning_codes": list(self._warning_codes),
                "shared_result_kinds": turn_results.public_kinds(),
                "document_focused": document_focused,
                "evidence_backed_clinical_conclusion": claims_complete,
                "claim_evidence_audit": claim_audit.model_dump(mode="json"),
                "route": route_decision.route.value,
                "route_reason": route_decision.reason_code,
                "plan_node_ids": [node.node_id for node in dynamic_plan.nodes],
                "model_preflight": preflight.model_dump(mode="json"),
                **governance_result,
            },
        )
        await turn_toolkit.memory_guard.commit_staged_write()
        for warning_code in turn_toolkit.memory_guard.warning_codes():
            if warning_code not in self._warning_codes:
                self._warning_codes.append(warning_code)
        if response.structured["warning_codes"] != list(self._warning_codes):
            response = response.model_copy(
                update={
                    "structured": {
                        **response.structured,
                        "warning_codes": list(self._warning_codes),
                    }
                }
            )
        await self._emit(
            stream_callback,
            "done",
            {
                "full_text": response.text,
                "references": [item.model_dump(mode="json") for item in response.citations],
                "safety": response.safety.model_dump(mode="json"),
            },
        )
        return response

    def _render_uploaded_documents(self) -> str:
        """Compatibility shim for existing tests and consumers."""
        return self._uploaded_input.render_documents()
