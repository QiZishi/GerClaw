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


class EvidenceAdmissionError(RuntimeError):
    """Stable failure for evidence that cannot be admitted."""


class EvidenceValidator(Protocol):
    def admit(self, record: EvidenceRecord) -> EvidenceRecord:
        """Validate source provenance and return an admitted immutable record."""
