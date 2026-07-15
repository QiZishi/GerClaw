"""Stable string enums persisted at API and database boundaries."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Supported account roles."""

    GUEST = "guest"
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"


class TraceStatus(StrEnum):
    """Lifecycle states for one system execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TraceEventType(StrEnum):
    """Allowlisted audit events; private model reasoning is intentionally absent."""

    AGENT_START = "agent.start"
    AGENT_FINISH = "agent.finish"
    MODEL_CALL = "model.call"
    RAG_RETRIEVE = "rag.retrieve"
    SEARCH_QUERY = "search.query"
    TOOL_CALL = "tool.call"
    SKILL_EXECUTE = "skill.execute"
    MEMORY_UPDATE = "memory.update"
    SAFETY_CHECK = "safety.check"
    VOICE_CALL = "voice.call"
    SYSTEM_ERROR = "system.error"


class TraceEventStatus(StrEnum):
    """Finite status vocabulary shared by all audit event types."""

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class FeedbackRating(StrEnum):
    """Explicit end-user feedback values."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class BadCaseSource(StrEnum):
    """Signals that can promote an execution into the bad-case queue."""

    EXECUTION_FAILURE = "execution_failure"
    NEGATIVE_FEEDBACK = "negative_feedback"


class BadCaseStatus(StrEnum):
    """Review workflow states for a bad case."""

    OPEN = "open"
    TRIAGED = "triaged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
