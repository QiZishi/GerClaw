"""Add encrypted immutable-track Skill evolution proposals.

Revision ID: c13c814f2058
Revises: b13c814f2057
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c13c814f2058"
down_revision: str | None = "b13c814f2057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_evolution_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("skill_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("candidate_revision", sa.Integer(), nullable=False),
        sa.Column("base_version", sa.String(length=32), nullable=False),
        sa.Column("candidate_version", sa.String(length=32), nullable=False),
        sa.Column("track", sa.String(length=16), nullable=False),
        sa.Column("object_kind", sa.String(length=32), nullable=False),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("review_state", sa.String(length=32), nullable=False),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("change_request", sa.Text(), nullable=False),
        sa.Column("base_snapshot", sa.Text(), nullable=False),
        sa.Column("candidate_snapshot", sa.Text(), nullable=False),
        sa.Column("base_content_hash", sa.String(length=64), nullable=False),
        sa.Column("candidate_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_revision > 0",
            name=op.f("ck_skill_evolution_proposals_positive_skill_proposal_base_revision"),
        ),
        sa.CheckConstraint(
            "candidate_revision = base_revision + 1",
            name=op.f("ck_skill_evolution_proposals_next_skill_proposal_candidate_revision"),
        ),
        sa.CheckConstraint(
            "track = 'immutable'",
            name=op.f("ck_skill_evolution_proposals_immutable_skill_proposal_track"),
        ),
        sa.CheckConstraint(
            "review_state = 'pending_offline_review'",
            name=op.f("ck_skill_evolution_proposals_pending_skill_proposal_review_state"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_evolution_proposals")),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "skill_id",
            "base_revision",
            "candidate_content_hash",
            name="uq_skill_proposals_owner_base_candidate",
        ),
    )
    op.create_index(
        op.f("ix_skill_evolution_proposals_tenant_id"),
        "skill_evolution_proposals",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_skill_evolution_proposals_actor_id"),
        "skill_evolution_proposals",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_proposals_owner_state_created",
        "skill_evolution_proposals",
        ["tenant_id", "actor_id", "review_state", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_skill_proposals_owner_state_created",
        table_name="skill_evolution_proposals",
    )
    op.drop_index(
        op.f("ix_skill_evolution_proposals_actor_id"),
        table_name="skill_evolution_proposals",
    )
    op.drop_index(
        op.f("ix_skill_evolution_proposals_tenant_id"),
        table_name="skill_evolution_proposals",
    )
    op.drop_table("skill_evolution_proposals")
