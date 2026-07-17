"""Strict contracts for synthetic, replay-safe evaluation cases."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.privacy_redaction.models import (
    EgressPurpose,
    RedactionFinding,
)

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
    policy_version: Literal["1.1.0"] = "1.1.0"
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
