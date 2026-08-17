"""Strict extraction, persistence, API, and vector DTOs for Memory."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, Final, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gerclaw_api.modules.memory.protocols import (
    MemoryAccessLevel,
    MemoryCategory,
    MemoryFactView,
    MemoryStatus,
    MemoryTombstoneReason,
    MemoryType,
)

MEMORY_MODEL_OUTPUT_SCHEMA_VERSION: Final[Literal["memory-extraction-model-output-v1"]] = (
    "memory-extraction-model-output-v1"
)


class MemoryFactDetails(BaseModel):
    """Finite structured attributes supported by profile extraction."""

    model_config = ConfigDict(extra="forbid")

    value: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=32)
    dose: str | None = Field(default=None, max_length=100)
    frequency: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=64)
    reaction: str | None = Field(default=None, max_length=200)
    severity: Literal["mild", "moderate", "severe", "unknown"] | None = None
    code: str | None = Field(default=None, max_length=32)
    level: str | None = Field(default=None, max_length=100)
    source_status: Literal["active", "stopped", "resolved", "historical", "unknown"] = "unknown"

    @field_validator(
        "value",
        "unit",
        "dose",
        "frequency",
        "route",
        "reaction",
        "code",
        "level",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            raise ValueError("memory detail text cannot be blank")
        return normalized


def validate_memory_fact_shape(
    *,
    category: MemoryCategory,
    entity: str,
    details: MemoryFactDetails,
) -> None:
    """Apply one deterministic category shape gate at every Memory write path."""

    normalized_entity = unicodedata.normalize("NFKC", entity).strip()
    if not normalized_entity:
        raise ValueError("memory entity cannot be blank")
    if category == "basic_info" and details.value is None:
        raise ValueError("basic information requires a value")
    if category == "medication" and entity.casefold() in {"药", "药物", "medication"}:
        raise ValueError("medication entity must name the medicine")
    if category == "vital_sign" and (details.value is None or details.unit is None):
        raise ValueError("vital sign requires value and unit")


class ProvenanceRecord(BaseModel):
    """记录记忆事实的来源信息"""

    model_config = ConfigDict(extra="forbid")

    source_type: Literal["user_report", "clinical_document", "lab_result", "imaging", "medication_list", "other"] = "user_report"
    source_reference: str | None = Field(default=None, max_length=500)  # 来源参考信息
    extraction_method: Literal["llm_extraction", "rule_based", "manual_entry", "imported"] = "llm_extraction"
    extraction_model: str | None = Field(default=None, max_length=100)  # 使用的模型
    confidence_score: float = Field(default=0.0, ge=0, le=1)  # 提取置信度
    verification_status: Literal["unverified", "auto_verified", "manual_verified", "disputed"] = "unverified"
    verified_by: str | None = Field(default=None, max_length=100)  # 验证者
    verified_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)  # 备注


class ConflictResolutionRecord(BaseModel):
    """记录冲突解决信息"""

    model_config = ConfigDict(extra="forbid")

    conflict_type: Literal["contradiction", "update", "negation", "ambiguity"] = "contradiction"
    conflicting_fact_ids: List[uuid.UUID] = Field(default_factory=list, max_length=10)
    resolution_strategy: Literal["latest_wins", "highest_confidence", "manual_review", "merge", "discard"] = "latest_wins"
    resolution_reason: str | None = Field(default=None, max_length=500)
    resolved_by: Literal["system", "user", "clinician"] = "system"
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
    original_values: Dict[str, Any] = Field(default_factory=dict)  # 原始值备份
    merged_values: Dict[str, Any] = Field(default_factory=dict)  # 合并后的值


class ExtractedMemoryFact(BaseModel):
    """One LLM candidate that still requires deterministic evidence validation."""

    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory
    memory_type: MemoryType
    entity: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=1_000)
    evidence_span: str = Field(min_length=1, max_length=300)
    action: Literal["upsert", "deactivate"] = "upsert"
    confidence: float = Field(ge=0, le=1)
    occurred_at: datetime | None = None
    details: MemoryFactDetails = Field(default_factory=MemoryFactDetails)

    # 新增字段：来源信息
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)

    # 新增字段：冲突解决记录
    conflict_resolution: ConflictResolutionRecord | None = None

    # 新增字段：失败原因记录
    fallback_reason: str | None = Field(default=None, max_length=200)

    @field_validator("entity", "statement", "evidence_span", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            raise ValueError("memory evidence text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_category_shape(self) -> ExtractedMemoryFact:
        """Reject category-specific candidates missing their identifying value."""

        validate_memory_fact_shape(
            category=self.category,
            entity=self.entity,
            details=self.details,
        )
        return self


class MemoryExtraction(BaseModel):
    """Bounded structured result produced by a real configured model."""

    model_config = ConfigDict(extra="forbid")

    model_output_schema_version: Literal["memory-extraction-model-output-v1"]
    facts: list[ExtractedMemoryFact] = Field(default_factory=list, max_length=30)


class MemoryUpdateResult(BaseModel):
    """Safe operational summary; it deliberately contains no fact text."""

    model_config = ConfigDict(extra="forbid")

    profile_version: int = Field(ge=0)
    changed_fact_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    confirmed_count: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)
    inactive_count: int = Field(default=0, ge=0)
    categories: list[MemoryCategory] = Field(default_factory=list, max_length=10)

    # 新增字段：冲突解决统计
    conflicts_detected: int = Field(default=0, ge=0)
    conflicts_resolved: int = Field(default=0, ge=0)

    # 新增字段：降级检索统计
    fallback_used: bool = Field(default=False)
    fallback_strategy: str | None = Field(default=None, max_length=50)
    fallback_reason: str | None = Field(default=None, max_length=200)


class MemoryVectorRecord(BaseModel):
    """Embedding input with identifiers separated from encrypted source text."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    category: MemoryCategory
    status: MemoryStatus
    revision: int = Field(ge=1)
    statement: str = Field(min_length=1, max_length=1_000)

    # 新增字段：时间戳
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MemoryVectorCandidate(BaseModel):
    """Qdrant result containing references only, never memory text."""

    model_config = ConfigDict(extra="forbid")

    fact_id: uuid.UUID
    revision: int = Field(ge=1)
    category: MemoryCategory
    score: float = Field(ge=0, le=1)

    # 新增字段：时间信息
    recorded_at: datetime | None = None
    updated_at: datetime | None = None


class HealthProfileRead(BaseModel):
    """Authenticated current-user health profile response."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    version: int = Field(ge=0)
    cross_session_recall_enabled: bool = True
    profile: dict[str, object]
    facts: list[MemoryFactView] = Field(default_factory=list, max_length=200)

    # 新增字段：冲突解决信息
    pending_conflicts: int = Field(default=0, ge=0)
    resolved_conflicts: int = Field(default=0, ge=0)


class MemoryFactCreateRequest(BaseModel):
    """Owner-authored fact that enters the same confirmation lifecycle as extraction."""

    model_config = ConfigDict(extra="forbid")

    expected_profile_version: int = Field(ge=0)
    category: MemoryCategory
    memory_type: MemoryType
    entity: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=1_000)
    details: MemoryFactDetails = Field(default_factory=MemoryFactDetails)
    access_level: MemoryAccessLevel = "standard"
    occurred_at: datetime | None = None

    # 新增字段：来源信息
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)

    @field_validator("entity", "statement", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            raise ValueError("memory owner text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_category_shape(self) -> MemoryFactCreateRequest:
        validate_memory_fact_shape(
            category=self.category,
            entity=self.entity,
            details=self.details,
        )
        return self


class MemoryFactUpdateRequest(BaseModel):
    """Revision-fenced correction that becomes proposed before re-confirmation."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    statement: str | None = Field(default=None, min_length=1, max_length=1_000)
    details: MemoryFactDetails | None = None
    access_level: MemoryAccessLevel | None = None
    occurred_at: datetime | None = None

    # 新增字段：冲突解决信息
    conflict_resolution: ConflictResolutionRecord | None = None

    @field_validator("statement", mode="before")
    @classmethod
    def normalize_statement(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value).strip()
        if not normalized:
            raise ValueError("memory statement cannot be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> MemoryFactUpdateRequest:
        mutable_fields = {"statement", "details", "access_level", "occurred_at", "conflict_resolution"}
        if not self.model_fields_set.intersection(mutable_fields):
            raise ValueError("memory fact update requires at least one mutable field")
        if "statement" in self.model_fields_set and self.statement is None:
            raise ValueError("memory statement cannot be null")
        semantic_fields = {"details", "occurred_at"}
        if self.model_fields_set.intersection(semantic_fields) and self.statement is None:
            raise ValueError("semantic memory changes require a new supporting statement")
        return self


class MemoryFactDeleteRequest(BaseModel):
    """Revision-fenced owner soft-delete."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    reason: MemoryTombstoneReason = "user_deleted"


class MemoryFactRestoreRequest(BaseModel):
    """Revision-fenced restoration of a caller-owned tombstone."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class MemoryFactDecisionRequest(BaseModel):
    """Optimistic user confirmation or retirement of one extracted fact."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    decision: Literal["confirm", "reject"]
    access_level: MemoryAccessLevel = "standard"

    # 新增字段：冲突解决决策
    conflict_resolution: ConflictResolutionRecord | None = None


class MemoryRecallPreferenceRequest(BaseModel):
    """Revision-fenced owner choice for cross-session recall."""

    model_config = ConfigDict(extra="forbid")

    expected_profile_version: int = Field(ge=0)
    enabled: bool


class MemoryRecallPreferenceRead(BaseModel):
    """Updated recall choice without returning health content."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    profile_version: int = Field(ge=1)


class MemoryFactDecisionRead(BaseModel):
    """Updated fact plus the resulting profile version."""

    model_config = ConfigDict(extra="forbid")

    fact: MemoryFactView
    profile_version: int = Field(ge=1)

    # 新增字段：冲突解决信息
    conflicts_resolved: int = Field(default=0, ge=0)


class MemoryFactMutationRead(BaseModel):
    """Current fact and profile projection after one owner CRUD mutation."""

    model_config = ConfigDict(extra="forbid")

    fact: MemoryFactView
    profile_version: int = Field(ge=1)

    # 新增字段：冲突解决信息
    conflicts_resolved: int = Field(default=0, ge=0)


class MemoryFactRevisionRead(BaseModel):
    """A caller-owned, immutable fact version saved before a later mutation."""

    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    activity: Literal[
        "legacy_update",
        "extraction_update",
        "user_decision",
        "user_update",
        "user_delete",
        "user_restore",
    ]
    category: MemoryCategory
    memory_type: MemoryType
    status: MemoryStatus
    access_level: MemoryAccessLevel = "standard"
    statement: str = Field(min_length=1, max_length=1_000)
    details: dict[str, object]
    confidence: float = Field(ge=0, le=1)
    source_trace_id: str | None = Field(default=None, max_length=64)
    occurred_at: datetime | None = None
    confirmed_at: datetime | None = None
    expires_at: datetime | None = None
    tombstoned_at: datetime | None = None
    tombstone_reason: MemoryTombstoneReason | None = None
    updated_at: datetime | None = None
    recorded_at: datetime

    # 新增字段：来源信息
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)

    # 新增字段：冲突解决记录
    conflict_resolution: ConflictResolutionRecord | None = None

    # 新增字段：失败原因
    fallback_reason: str | None = Field(default=None, max_length=200)


class MemoryFactHistoryRead(BaseModel):
    """Newest-first previous versions of one fact; current state remains in profile."""

    model_config = ConfigDict(extra="forbid")

    fact_id: uuid.UUID
    items: list[MemoryFactRevisionRead] = Field(default_factory=list, max_length=50)
