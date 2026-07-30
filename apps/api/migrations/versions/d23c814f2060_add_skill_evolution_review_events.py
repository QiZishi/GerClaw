"""Add append-only Skill evolution review events.

Revision ID: d23c814f2060
Revises: d13c814f2059
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d23c814f2060"
down_revision: str | None = "d13c814f2059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_evolution_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("approval_ticket_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            (
                "event_type IN "
                "('exported','paired_rejected','sealed_rejected','approved','activated','stale')"
            ),
            name=op.f("ck_skill_evolution_review_events_valid_skill_review_event_type"),
        ),
        sa.CheckConstraint(
            "sequence > 0",
            name=op.f("ck_skill_evolution_review_events_positive_skill_review_event_sequence"),
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["skill_evolution_proposals.id"],
            name=op.f("fk_skill_evolution_review_events_proposal_id_skill_evolution_proposals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_evolution_review_events")),
        sa.UniqueConstraint(
            "approval_ticket_digest",
            name="uq_skill_evolution_review_event_ticket",
        ),
        sa.UniqueConstraint(
            "proposal_id",
            "sequence",
            name="uq_skill_evolution_review_event_sequence",
        ),
    )
    op.create_index(
        "ix_skill_evolution_review_events_proposal_created",
        "skill_evolution_review_events",
        ["proposal_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_skill_evolution_review_events_terminal",
        "skill_evolution_review_events",
        ["proposal_id"],
        unique=True,
        postgresql_where=sa.text(
            "event_type IN ('paired_rejected','sealed_rejected','activated','stale')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_skill_evolution_review_events_terminal",
        table_name="skill_evolution_review_events",
    )
    op.drop_index(
        "ix_skill_evolution_review_events_proposal_created",
        table_name="skill_evolution_review_events",
    )
    op.drop_table("skill_evolution_review_events")
