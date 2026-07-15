"""Add durable Runtime HITL approvals.

Revision ID: f51c814f2020
Revises: e31c814f2019
Create Date: 2026-07-15 22:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON, EncryptedText

revision: str = "f51c814f2020"
down_revision: str | None = "e31c814f2019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_approvals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("requester_actor_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("invocation_id", sa.String(length=96), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=False),
        sa.Column("arguments", EncryptedJSON(), nullable=False),
        sa.Column("argument_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("required_roles", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("decided_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("decision_reason", EncryptedText(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execution_token_hash", sa.String(length=64), nullable=True),
        sa.Column("token_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result", EncryptedJSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','expired','cancelled')",
            name="valid_status",
        ),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.CheckConstraint("expires_at > created_at", name="future_expiry"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "session_id"],
            ["sessions.tenant_id", "sessions.user_id", "sessions.id"],
            name="fk_runtime_approvals_owner_session",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_runtime_approvals_tenant_idempotency"
        ),
        sa.UniqueConstraint(
            "tenant_id", "invocation_id", name="uq_runtime_approvals_tenant_invocation"
        ),
    )
    op.create_index(
        "ix_runtime_approvals_tenant_id", "runtime_approvals", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_runtime_approvals_trace_id", "runtime_approvals", ["trace_id"], unique=False
    )
    op.create_index(
        "ix_runtime_approvals_requester_actor_id",
        "runtime_approvals",
        ["requester_actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_approvals_tenant_status_expiry",
        "runtime_approvals",
        ["tenant_id", "status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_approvals_requester_created",
        "runtime_approvals",
        ["requester_actor_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_approvals_requester_created", table_name="runtime_approvals")
    op.drop_index("ix_runtime_approvals_tenant_status_expiry", table_name="runtime_approvals")
    op.drop_index("ix_runtime_approvals_requester_actor_id", table_name="runtime_approvals")
    op.drop_index("ix_runtime_approvals_trace_id", table_name="runtime_approvals")
    op.drop_index("ix_runtime_approvals_tenant_id", table_name="runtime_approvals")
    op.drop_table("runtime_approvals")
