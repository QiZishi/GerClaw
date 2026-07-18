"""Add encrypted local credentials and revocable refresh-session records.

Revision ID: f72c814f2030
Revises: f62c814f2029
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from gerclaw_api.encryption import EncryptedText

revision: str = "f72c814f2030"
down_revision: str | Sequence[str] | None = "f62c814f2029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("username", EncryptedText(), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("password_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("password_version > 0", name="positive_password_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "username_fingerprint", name="uq_account_credentials_name"
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_account_credentials_user"),
    )
    op.create_index("ix_account_credentials_tenant_id", "account_credentials", ["tenant_id"])
    op.create_index("ix_account_credentials_user_id", "account_credentials", ["user_id"])
    op.create_table(
        "account_refresh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("token_version > 0", name="positive_token_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_fingerprint", name="uq_account_refresh_sessions_token"),
    )
    op.create_index(
        "ix_account_refresh_sessions_tenant_id", "account_refresh_sessions", ["tenant_id"]
    )
    op.create_index("ix_account_refresh_sessions_user_id", "account_refresh_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_account_refresh_sessions_user_id", table_name="account_refresh_sessions")
    op.drop_index("ix_account_refresh_sessions_tenant_id", table_name="account_refresh_sessions")
    op.drop_table("account_refresh_sessions")
    op.drop_index("ix_account_credentials_user_id", table_name="account_credentials")
    op.drop_index("ix_account_credentials_tenant_id", table_name="account_credentials")
    op.drop_table("account_credentials")
