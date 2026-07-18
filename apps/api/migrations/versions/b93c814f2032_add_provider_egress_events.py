"""Add PHI-free provider egress audit events.

Revision ID: b93c814f2032
Revises: f82c814f2031
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b93c814f2032"
down_revision: str | Sequence[str] | None = "f82c814f2031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_egress_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("processor", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('external_search_query','external_tts')",
            name="valid_provider_egress_purpose",
        ),
        sa.CheckConstraint(
            "processor IN ('mimo_tts','anysearch','tavily')",
            name="valid_provider_egress_processor",
        ),
        sa.CheckConstraint(
            "outcome IN ('prepared','succeeded','failed')",
            name="valid_provider_egress_outcome",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_egress_events_tenant_id", "provider_egress_events", ["tenant_id"])
    op.create_index("ix_provider_egress_events_actor_id", "provider_egress_events", ["actor_id"])
    op.create_index(
        "ix_provider_egress_events_owner_created",
        "provider_egress_events",
        ["tenant_id", "actor_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_egress_events_owner_created", table_name="provider_egress_events")
    op.drop_index("ix_provider_egress_events_actor_id", table_name="provider_egress_events")
    op.drop_index("ix_provider_egress_events_tenant_id", table_name="provider_egress_events")
    op.drop_table("provider_egress_events")
