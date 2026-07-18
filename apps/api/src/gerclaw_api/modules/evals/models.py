"""Strict contracts for synthetic, replay-safe evaluation cases."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.memory.models import MemoryExtraction
from gerclaw_api.modules.memory.protocols import MemoryCategory, MemoryStatus
from gerclaw_api.modules.privacy_redaction.models import (
    EgressPurpose,
    RedactionFinding,
)
from gerclaw_api.modules.security_evaluation.models import SecurityAssetKind
from gerclaw_api.modules.skill.models import SkillDraftCheckCode

EVAL_CASE_SCHEMA_VERSION: Final = "eval-case-v1"


class EvalCase(BaseModel):
    """A reviewed synthetic case that cannot contain a user or patient identifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["eval-case-v1"] = "eval-case-v1"
    case_id: str = Field(pattern=r"^safety\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_input: str = Field(min_length=1, max_length=500)
    expected_high_risk_codes: tuple[str, ...] = ()
    expected_emergency_short_circuit: bool
    policy_version: Literal["medical_safety_v1"] = "medical_safety_v1"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"


class OutputSafetyEvalCase(BaseModel):
    """Reviewed synthetic public-output case for deterministic safety rewrites."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["eval-case-v1"] = "eval-case-v1"
    case_id: str = Field(pattern=r"^output-safety\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_output: str = Field(min_length=1, max_length=500)
    expected_public_output: str = Field(min_length=1, max_length=500)
    policy_version: Literal["medical_safety_v1"] = "medical_safety_v1"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"


class EvalCaseResult(BaseModel):
    """Machine-readable result without echoing synthetic or user input text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_high_risk_codes: tuple[str, ...]
    actual_high_risk_codes: tuple[str, ...]
    expected_emergency_short_circuit: bool
    actual_emergency_short_circuit: bool
    policy_version: str


class OutputSafetyEvalCaseResult(BaseModel):
    """Output-policy result without exposing either synthetic text field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    policy_version: str


class PrivacyRedactionEvalCase(BaseModel):
    """A reviewed synthetic egress canary for one privacy-policy version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["privacy-redaction-case-v1"] = "privacy-redaction-case-v1"
    case_id: str = Field(pattern=r"^privacy-redaction\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_input: str = Field(min_length=1, max_length=500)
    purpose: EgressPurpose
    expected_redacted_text: str = Field(min_length=1, max_length=500)
    expected_findings: tuple[RedactionFinding, ...] = Field(default_factory=tuple, max_length=6)
    policy_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"


class PrivacyRedactionEvalCaseResult(BaseModel):
    """PHI-free privacy canary result; neither source nor expected text is exposed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    purpose: EgressPurpose
    policy_version: str
    expected_findings: tuple[RedactionFinding, ...]
    actual_findings: tuple[RedactionFinding, ...]


class MedicationRuleEvalCase(BaseModel):
    """Reviewed synthetic regression case for deterministic medication rules."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["medication-rule-case-v1"] = "medication-rule-case-v1"
    case_id: str = Field(pattern=r"^medication-rule\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_medication_list: str = Field(min_length=1, max_length=2_000)
    patient_age: int | None = Field(default=None, ge=0, le=130)
    expected_finding_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    expected_source_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    expected_input_error: bool = False
    ruleset_version: Literal["medication-rules-v4"] = "medication-rules-v4"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"

    @field_validator("expected_finding_ids", "expected_source_ids")
    @classmethod
    def _validate_unique_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or not all(
            item and len(item) <= 96 and item.replace("_", "").replace("-", "").isalnum()
            for item in value
        ):
            raise ValueError("expected IDs must be unique bounded identifiers")
        return value

    @model_validator(mode="after")
    def validate_error_expectation(self) -> MedicationRuleEvalCase:
        if self.expected_input_error and (self.expected_finding_ids or self.expected_source_ids):
            raise ValueError("input-error cases cannot expect findings or source IDs")
        return self


class MedicationRuleEvalCaseResult(BaseModel):
    """PHI-free medication-rule result without the synthetic medication list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_finding_count: int = Field(ge=0)
    actual_finding_ids: tuple[str, ...]
    expected_source_count: int = Field(ge=0)
    actual_source_ids: tuple[str, ...]
    expected_input_error: bool
    actual_input_error: bool
    ruleset_version: str | None = None


class SkillDraftEvalCase(BaseModel):
    """Reviewed synthetic coverage expectation for a draft Skill checklist.

    This contract deliberately exercises only the deterministic review cues for
    a generated Skill. It does not evaluate medical validity, authorise a
    Skill, or retain a user request or provider response.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["skill-draft-case-v1"] = "skill-draft-case-v1"
    case_id: str = Field(pattern=r"^skill-draft\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_instructions: str = Field(min_length=20, max_length=8_000)
    tool_names: tuple[str, ...] = Field(default_factory=tuple, max_length=20)
    expected_missing_checks: tuple[SkillDraftCheckCode, ...] = Field(
        default_factory=tuple, max_length=4
    )
    quality_version: Literal["skill-draft-quality-v1"] = "skill-draft-quality-v1"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"

    @field_validator("tool_names")
    @classmethod
    def validate_unique_tool_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or not all(
            item and len(item) <= 64 and item.replace("_", "").replace("-", "").isalnum()
            for item in value
        ):
            raise ValueError("tool names must be unique bounded identifiers")
        return value

    @field_validator("expected_missing_checks")
    @classmethod
    def validate_unique_missing_checks(
        cls, value: tuple[SkillDraftCheckCode, ...]
    ) -> tuple[SkillDraftCheckCode, ...]:
        if len(set(value)) != len(value):
            raise ValueError("expected missing checks must be unique")
        return value


class SkillDraftEvalCaseResult(BaseModel):
    """PHI-free Skill-draft checklist result without draft instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_missing_checks: tuple[SkillDraftCheckCode, ...]
    actual_missing_checks: tuple[SkillDraftCheckCode, ...]
    quality_version: str


class RuntimeSecurityProfileEvalCase(BaseModel):
    """Reviewed, content-free regression case for a core Runtime profile gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["runtime-security-profile-case-v1"] = "runtime-security-profile-case-v1"
    case_id: str = Field(pattern=r"^runtime-security-profile\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    asset_kind: SecurityAssetKind
    asset_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    mutation: Literal["none", "version_mismatch", "missing_execution_budget"] = "none"
    expected_allowed: bool
    profile_version: Literal["1.0.0"] = "1.0.0"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"

    @model_validator(mode="after")
    def validate_core_asset_kind(self) -> RuntimeSecurityProfileEvalCase:
        if self.asset_kind not in {
            SecurityAssetKind.AGENT,
            SecurityAssetKind.MEMORY,
            SecurityAssetKind.RAG_SOURCE,
        }:
            raise ValueError("Runtime profile cases cover only Agent, Memory, and RAG source")
        return self


class RuntimeSecurityProfileEvalCaseResult(BaseModel):
    """PHI-free Runtime profile result without profile or request payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_allowed: bool
    actual_allowed: bool
    asset_kind: SecurityAssetKind
    profile_version: str


class MemoryExtractionEvalOutcome(BaseModel):
    """PHI-free expected outcome for one synthetic Memory candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: MemoryCategory
    status: MemoryStatus
    action: Literal["upsert", "deactivate"]


class MemoryExtractionEvalCase(BaseModel):
    """Reviewed synthetic regression case for deterministic Memory guards.

    The stored model response is synthetic test material only. Runner results
    intentionally expose category/status/action rather than user text, entities,
    statements, evidence spans, or model content.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["memory-extraction-case-v1"] = "memory-extraction-case-v1"
    case_id: str = Field(pattern=r"^memory-extraction\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_input: str = Field(min_length=1, max_length=500)
    synthetic_model_output: MemoryExtraction
    expected_outcomes: tuple[MemoryExtractionEvalOutcome, ...] = Field(
        default_factory=tuple, max_length=10
    )
    min_confidence: float = Field(default=0.8, ge=0, le=1)
    guard_version: Literal["memory-extraction-guard-v1"] = "memory-extraction-guard-v1"
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"


class MemoryExtractionEvalCaseResult(BaseModel):
    """PHI-free Memory extraction result without source or model content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_outcomes: tuple[MemoryExtractionEvalOutcome, ...]
    actual_outcomes: tuple[MemoryExtractionEvalOutcome, ...]
    guard_version: str


class RAGRetrievalEvalCase(BaseModel):
    """Reviewed synthetic retrieval expectation bound to one corpus index version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["eval-case-v1"] = "eval-case-v1"
    case_id: str = Field(pattern=r"^rag-retrieval\.[a-z0-9_.-]{3,80}$")
    title: str = Field(min_length=1, max_length=120)
    synthetic_query: str = Field(min_length=1, max_length=500)
    expected_document_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=10)
    required_source_types: tuple[
        Literal["guideline", "consensus", "textbook", "literature"], ...
    ] = ()
    minimum_expected_hits: int = Field(default=0, ge=0, le=10)
    expect_no_evidence: bool = False
    index_version: str = Field(min_length=1, max_length=64)
    provenance: Literal["synthetic_reviewed"] = "synthetic_reviewed"

    @staticmethod
    def _is_document_id(value: str) -> bool:
        return len(value) == 64 and all(character in "0123456789abcdef" for character in value)

    @field_validator("expected_document_ids")
    @classmethod
    def _validate_expected_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.casefold() for item in value)
        if len(set(normalized)) != len(normalized) or not all(
            cls._is_document_id(item) for item in normalized
        ):
            raise ValueError("expected_document_ids must be unique 64-character hexadecimal IDs")
        return normalized

    @field_validator("required_source_types")
    @classmethod
    def _validate_required_source_types(
        cls,
        value: tuple[Literal["guideline", "consensus", "textbook", "literature"], ...],
    ) -> tuple[Literal["guideline", "consensus", "textbook", "literature"], ...]:
        if len(value) > 4 or len(set(value)) != len(value):
            raise ValueError("required_source_types must contain at most four unique source types")
        return value

    @model_validator(mode="after")
    def validate_expectation(self) -> RAGRetrievalEvalCase:
        if self.expect_no_evidence:
            if (
                self.expected_document_ids
                or self.required_source_types
                or self.minimum_expected_hits != 0
            ):
                raise ValueError(
                    "no-evidence cases cannot declare expected document IDs, "
                    "source types, or minimum hits"
                )
            return self
        if not self.expected_document_ids or self.minimum_expected_hits < 1:
            raise ValueError(
                "evidence-match cases require expected document IDs and at least one minimum hit"
            )
        if self.minimum_expected_hits > len(self.expected_document_ids):
            raise ValueError("minimum_expected_hits cannot exceed expected_document_ids")
        return self


class RAGRetrievalEvalCaseSet(BaseModel):
    """Versioned, reviewed case-file envelope for one opt-in retrieval run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["rag-retrieval-case-set-v1"] = "rag-retrieval-case-set-v1"
    cases: tuple[RAGRetrievalEvalCase, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> RAGRetrievalEvalCaseSet:
        """Prevent a case file from silently running one case more than once."""

        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("RAG retrieval case IDs must be unique")
        return self


class RAGEvaluationRunConfig(BaseModel):
    """Explicitly opt-in, bounded external RAG evaluation configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    allow_external_rag: Literal[True]
    index_version: str = Field(min_length=1, max_length=64)
    top_k: int = Field(default=5, ge=1, le=20)
    max_cases: int = Field(default=20, ge=1, le=50)


class RAGRetrievalEvalCaseResult(BaseModel):
    """PHI-free retrieval result that never echoes a query, source, or content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    passed: bool
    expected_document_count: int = Field(ge=0)
    expected_no_evidence: bool
    matched_expected_document_count: int = Field(ge=0)
    returned_result_count: int = Field(ge=0)
    provenance_valid_result_count: int = Field(ge=0)
    matched_required_source_type_count: int = Field(ge=0)
    index_version: str


class RAGEvaluationRunReport(BaseModel):
    """Bounded report for one explicitly approved external retrieval run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["eval-run-v1"] = "eval-run-v1"
    kind: Literal["opt_in_rag_retrieval"] = "opt_in_rag_retrieval"
    external_model_or_rag: Literal[True] = True
    external_execution_opt_in: Literal[True] = True
    nondeterministic: Literal[True] = True
    index_version: str
    case_count: int = Field(ge=1, le=50)
    passed_count: int = Field(ge=0)
    top_k: int = Field(ge=1, le=20)
    results: tuple[RAGRetrievalEvalCaseResult, ...]
