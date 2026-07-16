"""Add encrypted caller-owned deterministic risk alerts.

Revision ID: d42c814f2027
Revises: c12d814f2026
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON

revision: str = "d42c814f2027"
down_revision: str | Sequence[str] | None = "c12d814f2026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("details", EncryptedJSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("acknowledgement_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("source IN ('cga')", name="valid_source"),
        sa.CheckConstraint("status IN ('active','acknowledged')", name="valid_status"),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_alerts")),
        sa.UniqueConstraint(
            "tenant_id", "actor_id", "source_fingerprint", name="uq_risk_alerts_owner_source"
        ),
    )
    op.create_index(op.f("ix_risk_alerts_tenant_id"), "risk_alerts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_risk_alerts_actor_id"), "risk_alerts", ["actor_id"], unique=False)
    op.create_index(
        "ix_risk_alerts_owner_status_updated",
        "risk_alerts",
        ["tenant_id", "actor_id", "status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_risk_alerts_owner_status_updated", table_name="risk_alerts")
    op.drop_index(op.f("ix_risk_alerts_actor_id"), table_name="risk_alerts")
    op.drop_index(op.f("ix_risk_alerts_tenant_id"), table_name="risk_alerts")
    op.drop_table("risk_alerts")
