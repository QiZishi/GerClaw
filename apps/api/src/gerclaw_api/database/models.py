"""PostgreSQL models for conversations, health profiles, traces, and feedback."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
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
    """Versioned, structured patient health profile stored as JSONB."""

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
