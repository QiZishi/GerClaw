"""add revisioned memory online CRUD tombstones

Revision ID: e13c814f2054
Revises: d93c814f2053
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e13c814f2054"
down_revision: str | None = "d93c814f2053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_facts",
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "memory_facts",
        sa.Column("tombstone_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "memory_facts",
        sa.Column("tombstone_previous_status", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_memory_facts_valid_tombstone_reason"),
        "memory_facts",
        "tombstone_reason IS NULL OR "
        "tombstone_reason IN ('user_deleted','outdated','incorrect','duplicate')",
    )
    op.create_check_constraint(
        op.f("ck_memory_facts_valid_tombstone_previous_status"),
        "memory_facts",
        "tombstone_previous_status IS NULL OR "
        "tombstone_previous_status IN "
        "('proposed','confirmed','conflicted','pending','inactive')",
    )
    op.create_check_constraint(
        op.f("ck_memory_facts_complete_tombstone"),
        "memory_facts",
        "(tombstoned_at IS NULL AND tombstone_reason IS NULL "
        "AND tombstone_previous_status IS NULL) OR "
        "(tombstoned_at IS NOT NULL AND tombstone_reason IS NOT NULL "
        "AND tombstone_previous_status IS NOT NULL AND status = 'inactive')",
    )
    op.add_column(
        "memory_fact_revisions",
        sa.Column(
            "activity",
            sa.String(length=32),
            server_default="legacy_update",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_memory_fact_revisions_valid_activity"),
        "memory_fact_revisions",
        "activity IN ('legacy_update','extraction_update','user_decision',"
        "'user_update','user_delete','user_restore')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_memory_fact_revisions_valid_activity"),
        "memory_fact_revisions",
        type_="check",
    )
    op.drop_column("memory_fact_revisions", "activity")
    op.drop_constraint(
        op.f("ck_memory_facts_complete_tombstone"),
        "memory_facts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_memory_facts_valid_tombstone_previous_status"),
        "memory_facts",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_memory_facts_valid_tombstone_reason"),
        "memory_facts",
        type_="check",
    )
    op.drop_column("memory_facts", "tombstone_previous_status")
    op.drop_column("memory_facts", "tombstone_reason")
    op.drop_column("memory_facts", "tombstoned_at")
