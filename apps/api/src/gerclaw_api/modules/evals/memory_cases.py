"""Reviewed synthetic Memory extraction guard cases; never use patient records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from gerclaw_api.modules.evals.models import (
    MemoryExtractionEvalCase,
    MemoryExtractionEvalOutcome,
)
from gerclaw_api.modules.memory.models import (
    MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
    ConflictResolutionRecord,
    ExtractedMemoryFact,
    MemoryExtraction,
    ProvenanceRecord,
)


def _allergy_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="allergy",
        memory_type="stable",
        entity="合成药甲",
        statement="用户自述对合成药甲过敏",
        evidence_span=evidence_span,
        confidence=0.95,
    )


def _medication_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="medication",
        memory_type="stable",
        entity="阿司匹林",
        statement="用户自述服用阿司匹林100mg",
        evidence_span=evidence_span,
        confidence=0.9,
    )


def _vital_sign_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="vital_sign",
        memory_type="evolving",
        entity="血压",
        statement="用户自述血压120/80mmHg",
        evidence_span=evidence_span,
        confidence=0.85,
    )


def _condition_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="condition",
        memory_type="stable",
        entity="高血压",
        statement="用户自述有高血压病史",
        evidence_span=evidence_span,
        confidence=0.9,
    )


def _event_candidate(*, evidence_span: str) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category="event",
        memory_type="event",
        entity="急诊",
        statement="用户自述昨天因胸痛急诊",
        evidence_span=evidence_span,
        confidence=0.95,
    )


# 基础提取质量测试用例
MEMORY_EXTRACTION_GOLDEN_CASES: tuple[MemoryExtractionEvalCase, ...] = (
    # 基础提取测试
    MemoryExtractionEvalCase(
        case_id="memory-extraction.self_report_confirmed",
        title="明确自述且证据一致的事实可以确认",
        synthetic_input="我对合成药甲过敏",
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
        synthetic_input="我没有合成药甲过敏",
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
        synthetic_input="我没有合成药乙过敏",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="我没有合成药乙过敏")],
        ),
    ),
    
    # Provenance功能测试用例
    MemoryExtractionEvalCase(
        case_id="memory-extraction.provenance_generation",
        title="provenance记录应包含来源信息",
        synthetic_input="我有高血压病史",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_condition_candidate(evidence_span="有高血压病史")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="condition", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.provenance_confidence",
        title="provenance应包含置信度信息",
        synthetic_input="血压120/80mmHg",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_vital_sign_candidate(evidence_span="血压120/80mmHg")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="vital_sign", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.provenance_source_type",
        title="不同类别应有不同的来源类型",
        synthetic_input="服用阿司匹林100mg",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_medication_candidate(evidence_span="服用阿司匹林100mg")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="medication", status="confirmed", action="upsert"),
        ),
    ),
    
    # 冲突检测测试用例
    MemoryExtractionEvalCase(
        case_id="memory-extraction.conflict_detection_negation",
        title="否定冲突应被检测并记录",
        synthetic_input="我没有过敏",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_allergy_candidate(evidence_span="没有过敏")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="allergy", status="inactive", action="deactivate"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.conflict_detection_update",
        title="更新冲突应被检测并记录",
        synthetic_input="现在血压140/90mmHg",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_vital_sign_candidate(evidence_span="血压140/90mmHg")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="vital_sign", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.conflict_detection_contradiction",
        title="矛盾冲突应被检测并记录",
        synthetic_input="有高血压病史但不服用阿司匹林",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[
                _condition_candidate(evidence_span="有高血压病史"),
                _medication_candidate(evidence_span="不服用阿司匹林"),
            ],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="condition", status="confirmed", action="upsert"),
            MemoryExtractionEvalOutcome(category="medication", status="inactive", action="deactivate"),
        ),
    ),
    
    # Fallback reason测试用例
    MemoryExtractionEvalCase(
        case_id="memory-extraction.fallback_reason_uncertainty",
        title="不确定性信息应记录fallback_reason",
        synthetic_input="可能有低血压",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_vital_sign_candidate(evidence_span="可能有低血压")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="vital_sign", status="pending", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.fallback_reason_low_confidence",
        title="低置信度信息应记录fallback_reason",
        synthetic_input="有人说有糖尿病",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_condition_candidate(evidence_span="有人说有糖尿病")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="condition", status="pending", action="upsert"),
        ),
    ),
    
    # 复杂场景测试
    MemoryExtractionEvalCase(
        case_id="memory-extraction.complex_medication_conflict",
        title="药物停用与继续用药的冲突检测",
        synthetic_input="服用阿司匹林一年后停药现在又开始服用",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[
                _medication_candidate(evidence_span="服用阿司匹林"),
                _medication_candidate(evidence_span="停药"),
                _medication_candidate(evidence_span="又开始服用"),
            ],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="medication", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.complex_condition_evolution",
        title="状态变化的冲突检测",
        synthetic_input="有高血压病史现已控制良好",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[_condition_candidate(evidence_span="有高血压病史")],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="condition", status="confirmed", action="upsert"),
        ),
    ),
    MemoryExtractionEvalCase(
        case_id="memory-extraction.complex_multiple_facts",
        title="多个事实同时提取",
        synthetic_input="有高血压病史服用阿司匹林100mg血压120/80mmHg",
        synthetic_model_output=MemoryExtraction(
            model_output_schema_version=MEMORY_MODEL_OUTPUT_SCHEMA_VERSION,
            facts=[
                _condition_candidate(evidence_span="有高血压病史"),
                _medication_candidate(evidence_span="服用阿司匹林100mg"),
                _vital_sign_candidate(evidence_span="血压120/80mmHg"),
            ],
        ),
        expected_outcomes=(
            MemoryExtractionEvalOutcome(category="condition", status="confirmed", action="upsert"),
            MemoryExtractionEvalOutcome(category="medication", status="confirmed", action="upsert"),
            MemoryExtractionEvalOutcome(category="vital_sign", status="confirmed", action="upsert"),
        ),
    ),
)