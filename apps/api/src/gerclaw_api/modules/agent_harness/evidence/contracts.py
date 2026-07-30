"""Evidence metadata required before a medical citation may be emitted."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    evidence_id: str = Field(min_length=1, max_length=128)
    source_type: Literal["knowledge_base", "web", "uploaded_document", "uploaded_image"]
    title: str = Field(min_length=1, max_length=500)
    institution: str | None = Field(default=None, max_length=300)
    year: int | None = Field(default=None, ge=1900, le=2200)
    source_version: str | None = Field(default=None, max_length=128)
    status: Literal["verified", "degraded", "unavailable"]
    locator: str | None = Field(default=None, min_length=1, max_length=1_000)
    adopted_text: str | None = Field(default=None, min_length=1, max_length=5_000)
    applicability: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def enforce_failure_semantics(self) -> "EvidenceRecord":
        if self.status == "unavailable":
            if self.locator is not None or self.adopted_text is not None:
                raise ValueError("unavailable evidence cannot contain locator or adopted text")
        elif self.locator is None or self.adopted_text is None:
            raise ValueError("usable evidence requires locator and adopted text")
        return self


class EvidenceClaimBinding(BaseModel):
    """One public answer segment bound to the exact citations it adopted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    claim_id: str = Field(pattern=r"^claim_[a-f0-9]{24}$")
    claim_excerpt: str = Field(min_length=1, max_length=1_000)
    citation_indices: tuple[int, ...] = Field(default=(), max_length=20)
    source_ids: tuple[str, ...] = Field(default=(), max_length=20)
    locators: tuple[str, ...] = Field(default=(), max_length=20)
    adopted_text_sha256: tuple[str, ...] = Field(default=(), max_length=20)
    status: Literal["bound", "unbound"]

    @model_validator(mode="after")
    def validate_binding_cardinality(self) -> "EvidenceClaimBinding":
        lengths = {
            len(self.citation_indices),
            len(self.source_ids),
            len(self.locators),
            len(self.adopted_text_sha256),
        }
        if len(lengths) != 1:
            raise ValueError("claim evidence binding fields must have equal length")
        if self.status == "bound" and not self.citation_indices:
            raise ValueError("bound claim requires at least one citation")
        if self.status == "unbound" and self.citation_indices:
            raise ValueError("unbound claim cannot contain citations")
        return self


class ClaimEvidenceAudit(BaseModel):
    """Deterministic terminal audit for claim-level evidence coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    claims: tuple[EvidenceClaimBinding, ...] = Field(default=(), max_length=100)
    clinical_claim_count: int = Field(ge=0, le=100)
    bound_claim_count: int = Field(ge=0, le=100)
    all_clinical_claims_bound: bool

    @model_validator(mode="after")
    def validate_counts(self) -> "ClaimEvidenceAudit":
        if self.clinical_claim_count != len(self.claims):
            raise ValueError("clinical claim count does not match bindings")
        if self.bound_claim_count != sum(claim.status == "bound" for claim in self.claims):
            raise ValueError("bound claim count does not match bindings")
        if self.all_clinical_claims_bound != (
            self.clinical_claim_count > 0 and self.bound_claim_count == self.clinical_claim_count
        ):
            raise ValueError("claim binding completion flag is inconsistent")
        return self


class EvidenceAdmissionError(RuntimeError):
    """Stable failure for evidence that cannot be admitted."""


class EvidenceValidator(Protocol):
    def admit(self, record: EvidenceRecord) -> EvidenceRecord:
        """Validate source provenance and return an admitted immutable record."""
