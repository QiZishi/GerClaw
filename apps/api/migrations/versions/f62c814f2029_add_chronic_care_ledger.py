"""Add encrypted chronic-care conditions and measurements.

Revision ID: f62c814f2029
Revises: e52c814f2028
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from gerclaw_api.encryption import EncryptedJSON

revision: str = "f62c814f2029"
down_revision: str | Sequence[str] | None = "e52c814f2028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chronic_care_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("details", EncryptedJSON(), nullable=False),
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
        sa.CheckConstraint(
            "confirmation_status IN ('self_reported')", name="valid_confirmation_status"
        ),
        sa.CheckConstraint("revision > 0", name="positive_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "actor_id", "id", name="uq_chronic_care_conditions_owner_id"
        ),
    )
    op.create_index(
        "ix_chronic_care_conditions_tenant_id", "chronic_care_conditions", ["tenant_id"]
    )
    op.create_index("ix_chronic_care_conditions_actor_id", "chronic_care_conditions", ["actor_id"])
    op.create_index(
        "ix_chronic_care_conditions_owner_updated",
        "chronic_care_conditions",
        ["tenant_id", "actor_id", "updated_at"],
    )
    op.create_table(
        "chronic_care_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("condition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("details", EncryptedJSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "actor_id", "condition_id"],
            [
                "chronic_care_conditions.tenant_id",
                "chronic_care_conditions.actor_id",
                "chronic_care_conditions.id",
            ],
            name="fk_chronic_care_measurements_owned_condition",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chronic_care_measurements_tenant_id", "chronic_care_measurements", ["tenant_id"]
    )
    op.create_index(
        "ix_chronic_care_measurements_actor_id", "chronic_care_measurements", ["actor_id"]
    )
    op.create_index(
        "ix_chronic_care_measurements_owner_condition_created",
        "chronic_care_measurements",
        ["tenant_id", "actor_id", "condition_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chronic_care_measurements_owner_condition_created",
        table_name="chronic_care_measurements",
    )
    op.drop_index("ix_chronic_care_measurements_actor_id", table_name="chronic_care_measurements")
    op.drop_index("ix_chronic_care_measurements_tenant_id", table_name="chronic_care_measurements")
    op.drop_table("chronic_care_measurements")
    op.drop_index("ix_chronic_care_conditions_owner_updated", table_name="chronic_care_conditions")
    op.drop_index("ix_chronic_care_conditions_actor_id", table_name="chronic_care_conditions")
    op.drop_index("ix_chronic_care_conditions_tenant_id", table_name="chronic_care_conditions")
    op.drop_table("chronic_care_conditions")
