"""Reviewed synthetic Memory extraction guard cases; never use patient records."""

from __future__ import annotations

from gerclaw_api.modules.evals.models import (
    MemoryExtractionEvalCase,
    MemoryExtractionEvalOutcome,
)
from gerclaw_api.modules.memory.models import (
    MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
    ExtractedMemoryFact,
    MemoryExtraction,
)


def _allergy_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="allergy",
        memory_type="stable",
        entity="合成药甲",
        statement="合成患者自述对合成药甲过敏",
        evidence_span=evidence_span,
        confidence=0.95,
    )


MEMORY_EXTRACTION_GOLDEN_CASES: tuple[MemoryExtractionEvalCase, ...] = (
    MemoryExtractionEvalCase(
        case_id="memory-extraction.self_report_confirmed",
        title="明确自述且证据一致的事实可以确认",
        synthetic_input="我对合成药甲过敏。",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="我对合成药甲过敏")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="allergy", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.negated_fact_inactive",
        title="否定证据不得变成正向确认",
        synthetic_input="我没有合成药甲过敏。",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="没有合成药甲过敏")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="allergy", status="inactive", action="deactivate"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.other_subject_rejected",
        title="他人健康信息不得写入当前用户画像",
        synthetic_input="我母亲对合成药甲过敏。",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="我母亲对合成药甲过敏")],
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.unbound_entity_rejected",
        title="实体未被输入证据支持时不得保留",
        synthetic_input="我对合成药乙过敏。",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="我对合成药乙过敏")],
        ),
    ),
)
