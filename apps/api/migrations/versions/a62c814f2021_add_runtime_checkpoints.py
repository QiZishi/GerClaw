"""Add encrypted Runtime checkpoints.

Revision ID: a62c814f2021
Revises: f51c814f2020
Create Date: 2026-07-15 23:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON

revision: str = "a62c814f2021"
down_revision: str | None = "f51c814f2020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_checkpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("approval_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("workflow_version", sa.String(length=32), nullable=False),
        sa.Column("capability_versions", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("state", EncryptedJSON(), nullable=False),
        sa.Column("state_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="parked", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("sequence > 0", name="positive_sequence"),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.CheckConstraint("status IN ('parked','resumed','discarded')", name="valid_status"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "session_id"],
            ["sessions.tenant_id", "sessions.user_id", "sessions.id"],
            name="fk_runtime_checkpoints_owner_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["runtime_approvals.id"],
            name="fk_runtime_checkpoints_approval",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "trace_id",
            "sequence",
            name="uq_runtime_checkpoints_trace_sequence",
        ),
    )
    op.create_index(
        "ix_runtime_checkpoints_tenant_id", "runtime_checkpoints", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_runtime_checkpoints_actor_id", "runtime_checkpoints", ["actor_id"], unique=False
    )
    op.create_index(
        "ix_runtime_checkpoints_trace_id", "runtime_checkpoints", ["trace_id"], unique=False
    )
    op.create_index(
        "ix_runtime_checkpoints_owner_status",
        "runtime_checkpoints",
        ["tenant_id", "actor_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_checkpoints_owner_status", table_name="runtime_checkpoints")
    op.drop_index("ix_runtime_checkpoints_trace_id", table_name="runtime_checkpoints")
    op.drop_index("ix_runtime_checkpoints_actor_id", table_name="runtime_checkpoints")
    op.drop_index("ix_runtime_checkpoints_tenant_id", table_name="runtime_checkpoints")
    op.drop_table("runtime_checkpoints")
