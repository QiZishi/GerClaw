"""Add immutable Trace start and per-turn chat idempotency.

Revision ID: 8a6d5b012016
Revises: f196f3600b8c
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "8a6d5b012016"
down_revision: str | None = "f196f3600b8c"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "execution_traces",
        sa.Column("start_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_messages_tenant_trace_user",
        "messages",
        ["tenant_id", "trace_id"],
        unique=True,
        postgresql_where=sa.text("role = 'user' AND trace_id IS NOT NULL"),
    )
    op.create_index(
        "uq_messages_tenant_trace_assistant",
        "messages",
        ["tenant_id", "trace_id"],
        unique=True,
        postgresql_where=sa.text("role = 'assistant' AND trace_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_tenant_trace_assistant", table_name="messages")
    op.drop_index("uq_messages_tenant_trace_user", table_name="messages")
    op.drop_column("execution_traces", "start_fingerprint")
