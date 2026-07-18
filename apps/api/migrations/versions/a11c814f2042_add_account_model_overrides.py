"""Add encrypted account-scoped Agent model overrides.

Revision ID: a11c814f2042
Revises: c36d914f3150
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a11c814f2042"
down_revision: str | Sequence[str] | None = "c36d914f3150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_model_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        # EncryptedJSON serializes to authenticated ciphertext, so its physical
        # representation must be text rather than PostgreSQL JSONB.
        sa.Column("configuration", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="positive_account_model_override_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "actor_id", name="uq_account_model_override_owner"),
    )
    op.create_index("ix_account_model_overrides_tenant_id", "account_model_overrides", ["tenant_id"])
    op.create_index("ix_account_model_overrides_actor_id", "account_model_overrides", ["actor_id"])


def downgrade() -> None:
    op.drop_index("ix_account_model_overrides_actor_id", table_name="account_model_overrides")
    op.drop_index("ix_account_model_overrides_tenant_id", table_name="account_model_overrides")
    op.drop_table("account_model_overrides")
