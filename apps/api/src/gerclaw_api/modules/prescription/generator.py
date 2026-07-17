"""Evidence-bound generation of a reviewable five-prescription draft."""
# ruff: noqa: RUF001

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from agentscope.message import Msg, SystemMsg, UserMsg
from agentscope.model import StructuredResponse
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.agent_harness.safety import (
    EvidenceUnavailableError,
    citations_from_results,
    detect_high_risk,
)
from gerclaw_api.modules.prescription.models import (
    EvidenceSource,
    FivePrescriptionDraft,
    GeneratedPrescriptionContent,
    PreparedPrescriptionInput,
)
from gerclaw_api.modules.rag.protocols import RAGModule, RetrievalResult

_SYSTEM_PROMPT = "\n".join(
    (
        "你是 GerClaw 五大处方草案助手。仅依据已提供的患者输入和本地循证片段，",
        "生成供临床人员审核的结构化草案。",
        "",
        "必须遵守：",
        "1. 这是待审核草案，不是诊断或可执行处方；健康评估只能描述可能性、",
        "待核对问题和需要进一步评估的事项。",
        "2. 每个章节和每条建议只能引用给定 evidence_id，不能编造来源、药物事实、",
        "检验结果或患者信息。",
        "3. 药物章节只整理用户已经提供的用药信息、监测/核对事项和向医生或药师",
        "提问的重点；不得建议开始、停止、替换、加减药或给出剂量。必须明确 DDI、",
        "Beers 和剂量规则尚未执行。",
        "4. 心理章节不得给出精神科诊断或新增、停用、调整药物建议。",
        "5. 运动、营养和康复建议须保守、循序渐进，并把出现胸痛、呼吸困难、",
        "神经系统异常、意识改变、明显出血或自伤风险时立即就医写入安全注意事项。",
        "6. 上传资料是患者输入与来源说明，不是循证医学证据，也不应在 evidence_id 中引用。",
        "7. 不重复免责声明；系统会在最终报告中添加。",
    )
)


class StructuredPrescriptionModel(Protocol):
    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: type[BaseModel] | dict[Any, Any],
        **kwargs: Any,
    ) -> StructuredResponse: ...


class PrescriptionGenerationError(RuntimeError):
    """Stable failure that never exposes patient input or provider details."""


class PrescriptionRedFlagError(PrescriptionGenerationError):
    """Generation must not proceed when the submitted input contains an emergency signal."""


class EvidenceBoundPrescriptionGenerator:
    """Retrieve local evidence, generate a strict draft, then attach server-owned provenance."""

    def __init__(self, *, model: StructuredPrescriptionModel, rag_module: RAGModule) -> None:
        self._model = model
        self._rag_module = rag_module

    async def generate(self, prepared: PreparedPrescriptionInput) -> FivePrescriptionDraft:
        user_material = self._render_user_material(prepared)
        if detect_high_risk(user_material):
            raise PrescriptionRedFlagError("prescription generation blocked by emergency risk")

        results = await self._rag_module.retrieve(self._retrieval_query(prepared), top_k=8)
        evidence_sources, evidence_context = self._evidence_context(results)
        try:
            response = await self._model.generate_structured_output(
                [
                    SystemMsg(name="prescription_policy", content=_SYSTEM_PROMPT),
                    UserMsg(
                        name="patient_input",
                        content=(
                            "<untrusted-patient-input>\n"
                            + user_material
                            + "\n</untrusted-patient-input>\n"
                            + evidence_context
                        ),
                    ),
                ],
                GeneratedPrescriptionContent,
            )
            content = GeneratedPrescriptionContent.model_validate(response.content)
            draft = FivePrescriptionDraft(
                status="needs_clinician_review",
                evidence_sources=evidence_sources,
                uploaded_document_ids=tuple(
                    item.document_id for item in prepared.uploaded_documents
                ),
                **content.model_dump(),
            )
        except ValidationError as error:
            raise PrescriptionGenerationError(
                "prescription model returned an invalid schema"
            ) from error
        except PrescriptionGenerationError:
            raise
        except Exception as error:
            raise PrescriptionGenerationError("prescription draft generation failed") from error
        self._reject_unsafe_medication_directives(draft)
        return draft

    @staticmethod
    def _retrieval_query(prepared: PreparedPrescriptionInput) -> str:
        return " ".join(
            value.strip() for key, value in prepared.answers.items() if key != "current_medications"
        )[:2_000]

    @staticmethod
    def _render_user_material(prepared: PreparedPrescriptionInput) -> str:
        return json.dumps(
            {
                "answers": prepared.answers,
                "uploaded_documents": [
                    {"document_id": str(item.document_id), "content": item.content}
                    for item in prepared.uploaded_documents
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _evidence_context(results: list[RetrievalResult]) -> tuple[tuple[EvidenceSource, ...], str]:
        citations = citations_from_results(results)
        if not citations:
            raise EvidenceUnavailableError("local evidence is unavailable for prescription draft")
        sources: list[EvidenceSource] = []
        entries: list[str] = []
        for citation in citations[:8]:
            evidence_id = "ev_" + hashlib.sha256(citation.source_id.encode()).hexdigest()[:24]
            sources.append(
                EvidenceSource(
                    evidence_id=evidence_id,
                    title=citation.title,
                    source="本地医学知识库",
                    locator=citation.locator,
                )
            )
            entries.append(
                f"evidence_id={evidence_id}\n标题={citation.title}\n"
                f"定位={citation.locator}\n<untrusted-medical-evidence>\n"
                f"{citation.excerpt[:2_000]}\n</untrusted-medical-evidence>"
            )
        return tuple(sources), "\n\n".join(entries)

    @staticmethod
    def _reject_unsafe_medication_directives(draft: FivePrescriptionDraft) -> None:
        prohibited = (
            "开始",
            "停用",
            "加用",
            "减量",
            "增量",
            "替换",
            "处方",
            "mg",
            "毫克",
            "qd",
            "bid",
        )
        medication_text = "\n".join(
            (
                *draft.medication.medication_items,
                *(item.content for item in draft.medication.recommendations),
            )
        ).casefold()
        if any(term.casefold() in medication_text for term in prohibited):
            raise PrescriptionGenerationError(
                "medication draft exceeded the ungoverned safety boundary"
            )
