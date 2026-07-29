"""govern memory recall and proposals

Revision ID: c83c814f2052
Revises: f72c814f2051
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c83c814f2052"
down_revision: str | None = "f72c814f2051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "health_profiles",
        sa.Column(
            "cross_session_recall_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.drop_constraint(
        op.f("ck_memory_facts_valid_status"),
        "memory_facts",
        type_="check",
    )
    op.execute("UPDATE memory_facts SET status = 'proposed' WHERE status = 'pending'")
    op.create_check_constraint(
        op.f("ck_memory_facts_valid_status"),
        "memory_facts",
        "status IN ('proposed','confirmed','conflicted','pending','inactive')",
    )
    op.add_column(
        "memory_facts",
        sa.Column(
            "access_level",
            sa.String(length=16),
            server_default="standard",
            nullable=False,
        ),
    )
    op.add_column(
        "memory_facts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_memory_facts_valid_access_level"),
        "memory_facts",
        "access_level IN ('standard','restricted')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_memory_facts_valid_access_level"),
        "memory_facts",
        type_="check",
    )
    op.drop_column("memory_facts", "expires_at")
    op.drop_column("memory_facts", "access_level")
    op.drop_constraint(
        op.f("ck_memory_facts_valid_status"),
        "memory_facts",
        type_="check",
    )
    op.execute(
        "UPDATE memory_facts SET status = 'pending' "
        "WHERE status IN ('proposed','conflicted')"
    )
    op.create_check_constraint(
        op.f("ck_memory_facts_valid_status"),
        "memory_facts",
        "status IN ('confirmed','pending','inactive')",
    )
    op.drop_column("health_profiles", "cross_session_recall_enabled")
