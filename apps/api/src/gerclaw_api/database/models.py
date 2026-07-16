"""PostgreSQL models for conversations, health profiles, traces, and feedback."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from gerclaw_api.database.base import Base
from gerclaw_api.encryption import EncryptedJSON, EncryptedText


class TimestampMixin:
    """UTC timestamps maintained by PostgreSQL."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    """Account or pseudonymous guest identity."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_users_tenant_external"),
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id"),
        UniqueConstraint("tenant_id", "external_id", "id", name="uq_users_tenant_external_id"),
        CheckConstraint("role IN ('guest','patient','doctor','admin')", name="valid_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class ConversationSession(TimestampMixin, Base):
    """Durable user conversation independent from AgentScope hot state."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active','archived','deleted')", name="valid_status"),
        UniqueConstraint("tenant_id", "user_id", "id", name="uq_sessions_tenant_user_id"),
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    active_fencing_token: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    active_fencing_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_summary: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSON(), default=dict, nullable=False
    )


class Message(Base):
    """One validated user, assistant, system, or tool message."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system','tool')", name="valid_role"),
        Index("ix_messages_tenant_session_created", "tenant_id", "session_id", "created_at"),
        Index(
            "uq_messages_tenant_trace_user",
            "tenant_id",
            "trace_id",
            unique=True,
            postgresql_where=text("role = 'user' AND trace_id IS NOT NULL"),
        ),
        Index(
            "uq_messages_tenant_trace_assistant",
            "tenant_id",
            "trace_id",
            unique=True,
            postgresql_where=text("role = 'assistant' AND trace_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[list[dict[str, Any]]] = mapped_column(EncryptedJSON(), nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", EncryptedJSON(), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HealthProfile(TimestampMixin, Base):
    """Versioned patient profile stored in one AES-GCM encrypted column."""

    __tablename__ = "health_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_health_profiles_tenant_user"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    profile: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict, nullable=False)


class CgaAssessment(TimestampMixin, Base):
    """One caller-owned, encrypted CGA screening assessment."""

    __tablename__ = "cga_assessments"
    __table_args__ = (
        CheckConstraint("status IN ('active','completed','abandoned')", name="valid_status"),
        CheckConstraint("current_position >= 1 AND current_position <= 30", name="valid_position"),
        CheckConstraint("revision > 0", name="positive_revision"),
        Index("ix_cga_assessments_owner_updated", "tenant_id", "actor_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scale_id: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    current_position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict, nullable=False)
    notes: Mapped[dict[str, Any] | None] = mapped_column(
        EncryptedJSON(), default=dict, nullable=True
    )
    report: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON(), nullable=True)


class UploadedDocument(TimestampMixin, Base):
    """Encrypted, revocable parsed document scoped to one conversation owner."""

    __tablename__ = "uploaded_documents"
    __table_args__ = (
        CheckConstraint("status IN ('active','revoked')", name="valid_status"),
        CheckConstraint("content_characters > 0", name="positive_content_characters"),
        Index(
            "ix_uploaded_documents_owner_session_active",
            "tenant_id",
            "actor_id",
            "session_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    media_type: Mapped[str] = mapped_column(String(96), nullable=False)
    parse_source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    content: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    content_characters: Mapped[int] = mapped_column(Integer, nullable=False)


class ClinicalIntake(TimestampMixin, Base):
    """Encrypted, caller-owned non-clinical intake for future governed workflows."""

    __tablename__ = "clinical_intakes"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('prescription','medication_review')", name="valid_clinical_intake_kind"
        ),
        CheckConstraint(
            "status IN ('collecting','information_complete_pending_governance')",
            name="valid_clinical_intake_status",
        ),
        CheckConstraint("revision > 0", name="positive_clinical_intake_revision"),
        UniqueConstraint(
            "tenant_id",
            "actor_id",
            "session_id",
            "kind",
            name="uq_clinical_intakes_principal_session_kind",
        ),
        Index(
            "ix_clinical_intakes_owner_session_updated",
            "tenant_id",
            "actor_id",
            "session_id",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="collecting")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    answers: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict, nullable=False)


class MemoryFact(TimestampMixin, Base):
    """One encrypted, evidenced user-memory fact with a vector revision."""

    __tablename__ = "memory_facts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "fact_key", name="uq_memory_facts_tenant_user_key"
        ),
        CheckConstraint(
            "category IN ('basic_info','allergy','condition','medication','vital_sign',"
            "'assessment','event','social','preference','goal')",
            name="valid_category",
        ),
        CheckConstraint("memory_type IN ('stable','evolving','event')", name="valid_memory_type"),
        CheckConstraint("status IN ('confirmed','pending','inactive')", name="valid_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_confidence"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("vector_revision >= 0", name="nonnegative_vector_revision"),
        Index("ix_memory_facts_tenant_user_status", "tenant_id", "user_id", "status"),
        Index("ix_memory_facts_vector_sync", "status", "revision", "vector_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    source_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    statement: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    vector_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryFactRevision(Base):
    """Immutable encrypted snapshot of a Memory fact before each mutation."""

    __tablename__ = "memory_fact_revisions"
    __table_args__ = (
        UniqueConstraint("fact_id", "revision", name="uq_memory_fact_revisions_fact_revision"),
        CheckConstraint("revision > 0", name="positive_revision"),
        Index(
            "ix_memory_fact_revisions_tenant_user_created",
            "tenant_id",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory_facts.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SkillDefinitionRecord(TimestampMixin, Base):
    """Current encrypted caller-owned Skill definition."""

    __tablename__ = "skill_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "actor_id", "skill_id", name="uq_skill_definitions_owner_skill"
        ),
        UniqueConstraint(
            "tenant_id",
            "actor_id",
            "name_fingerprint",
            name="uq_skill_definitions_owner_name",
        ),
        UniqueConstraint("tenant_id", "actor_id", "id", name="uq_skill_definitions_owner_id"),
        CheckConstraint("origin IN ('text','upload','generated')", name="valid_origin"),
        CheckConstraint("revision > 0", name="positive_revision"),
        Index(
            "ix_skill_definitions_owner_updated",
            "tenant_id",
            "actor_id",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    name_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    tool_names: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    source_markdown: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SkillDefinitionRevision(Base):
    """Immutable encrypted snapshot retained before a custom Skill mutation."""

    __tablename__ = "skill_definition_revisions"
    __table_args__ = (
        UniqueConstraint(
            "skill_definition_id",
            "revision",
            name="uq_skill_definition_revisions_record_revision",
        ),
        CheckConstraint("revision > 0", name="positive_revision"),
        ForeignKeyConstraint(
            ["tenant_id", "actor_id", "skill_definition_id"],
            [
                "skill_definitions.tenant_id",
                "skill_definitions.actor_id",
                "skill_definitions.id",
            ],
            name="fk_skill_revisions_owner_definition",
            ondelete="CASCADE",
        ),
        Index(
            "ix_skill_definition_revisions_owner_created",
            "tenant_id",
            "actor_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    skill_definition_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SessionSkill(Base):
    """Ordered Skill selection for one caller-owned durable conversation."""

    __tablename__ = "session_skills"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "session_id", "skill_id", name="uq_session_skills_session_skill"
        ),
        UniqueConstraint(
            "tenant_id", "session_id", "position", name="uq_session_skills_session_position"
        ),
        CheckConstraint("position >= 0 AND position < 10", name="valid_position"),
        ForeignKeyConstraint(
            ["tenant_id", "actor_id", "user_id"],
            ["users.tenant_id", "users.external_id", "users.id"],
            name="fk_session_skills_owner_principal",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "session_id"],
            ["sessions.tenant_id", "sessions.user_id", "sessions.id"],
            name="fk_session_skills_owner_session",
            ondelete="CASCADE",
        ),
        Index("ix_session_skills_owner_session", "tenant_id", "actor_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RuntimeApproval(TimestampMixin, Base):
    """Durable, tenant-scoped HITL request with a one-time execution grant."""

    __tablename__ = "runtime_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','cancelled')",
            name="valid_status",
        ),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("expires_at > created_at", name="future_expiry"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_runtime_approvals_tenant_idempotency"
        ),
        UniqueConstraint(
            "tenant_id", "invocation_id", name="uq_runtime_approvals_tenant_invocation"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "session_id"],
            ["sessions.tenant_id", "sessions.user_id", "sessions.id"],
            name="fk_runtime_approvals_owner_session",
            ondelete="CASCADE",
        ),
        Index("ix_runtime_approvals_tenant_status_expiry", "tenant_id", "status", "expires_at"),
        Index("ix_runtime_approvals_requester_created", "requester_actor_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requester_actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invocation_id: Mapped[str] = mapped_column(String(96), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), nullable=False)
    argument_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    required_roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    decided_by_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON(), nullable=True)


class RuntimeCheckpointRecord(TimestampMixin, Base):
    """Encrypted, version-bound Agent state parked at a Runtime suspension point."""

    __tablename__ = "runtime_checkpoints"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="positive_sequence"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("status IN ('parked','resumed','discarded')", name="valid_status"),
        UniqueConstraint(
            "tenant_id", "trace_id", "sequence", name="uq_runtime_checkpoints_trace_sequence"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id", "session_id"],
            ["sessions.tenant_id", "sessions.user_id", "sessions.id"],
            name="fk_runtime_checkpoints_owner_session",
            ondelete="CASCADE",
        ),
        Index("ix_runtime_checkpoints_owner_status", "tenant_id", "actor_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approval_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runtime_approvals.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(32), nullable=False)
    capability_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), nullable=False)
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="parked", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionTrace(Base):
    """Top-level audit record for one complete system execution."""

    __tablename__ = "execution_traces"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="valid_status",
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="nonnegative_duration"),
        UniqueConstraint("tenant_id", "trace_id", name="uq_execution_traces_tenant_trace"),
        Index("ix_execution_traces_tenant_started", "tenant_id", "started_at"),
        Index("ix_execution_traces_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    execution_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running", nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    start_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    finish_idempotency_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    finish_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TraceEvent(Base):
    """Ordered, redacted event emitted during one execution."""

    __tablename__ = "trace_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "trace_id"),
            ("execution_traces.tenant_id", "execution_traces.trace_id"),
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "trace_id", "sequence", name="uq_trace_events_sequence"),
        UniqueConstraint("tenant_id", "trace_id", "event_id", name="uq_trace_events_event"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="nonnegative_duration"),
        Index("ix_trace_events_trace_created", "trace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(96), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserFeedback(Base):
    """Idempotent feedback tied to an execution trace."""

    __tablename__ = "user_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "trace_id"),
            ("execution_traces.tenant_id", "execution_traces.trace_id"),
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_feedback_tenant_idempotency"),
        CheckConstraint("rating IN ('positive','negative')", name="valid_rating"),
        Index("ix_user_feedback_trace_created", "trace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    comment: Mapped[str | None] = mapped_column(EncryptedText(), nullable=True)
    feedback_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BadCase(Base):
    """Review queue item created from failures or negative feedback."""

    __tablename__ = "bad_cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "trace_id"),
            ("execution_traces.tenant_id", "execution_traces.trace_id"),
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "trace_id", "source", name="uq_bad_cases_trace_source"),
        CheckConstraint("source IN ('execution_failure','negative_feedback')", name="valid_source"),
        CheckConstraint("status IN ('open','triaged','resolved','dismissed')", name="valid_status"),
        CheckConstraint("severity IN ('low','medium','high','critical')", name="valid_severity"),
        Index("ix_bad_cases_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_feedback.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON(), default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
