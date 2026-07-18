"""Add immutable PHI-free local-account security audit events.

Revision ID: f82c814f2031
Revises: f72c814f2030
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f82c814f2031"
down_revision: str | Sequence[str] | None = "f72c814f2030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("subject_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('register','login','refresh','logout','password_change')",
            name="valid_identity_security_event_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded','rejected','ignored')",
            name="valid_identity_security_event_outcome",
        ),
        sa.CheckConstraint(
            "role IS NULL OR role IN ('patient','doctor')",
            name="valid_identity_security_event_role",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_identity_security_events_tenant_id", "identity_security_events", ["tenant_id"]
    )
    op.create_index(
        "ix_identity_security_events_tenant_subject_created",
        "identity_security_events",
        ["tenant_id", "subject_fingerprint", "created_at"],
    )
    op.create_index(
        "ix_identity_security_events_tenant_actor_created",
        "identity_security_events",
        ["tenant_id", "actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_security_events_tenant_actor_created",
        table_name="identity_security_events",
    )
    op.drop_index(
        "ix_identity_security_events_tenant_subject_created",
        table_name="identity_security_events",
    )
    op.drop_index("ix_identity_security_events_tenant_id", table_name="identity_security_events")
    op.drop_table("identity_security_events")
