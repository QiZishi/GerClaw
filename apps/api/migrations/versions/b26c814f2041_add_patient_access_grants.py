"""Add patient-controlled doctor read-access grants.

Revision ID: b26c814f2041
Revises: b16c814f2040
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b26c814f2041"
down_revision: str | Sequence[str] | None = "b16c814f2040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("patient_actor_id", sa.String(length=128), nullable=False),
        sa.Column("doctor_actor_id", sa.String(length=128), nullable=False),
        sa.Column("resource_scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "resource_scope IN ('health_profile_read','cga_report_read')",
            name="valid_patient_access_grant_resource_scope",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')", name="valid_patient_access_grant_status"
        ),
        sa.CheckConstraint("revision > 0", name="positive_patient_access_grant_revision"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "patient_actor_id",
            "doctor_actor_id",
            "resource_scope",
            name="uq_patient_access_grants_subject_doctor_resource",
        ),
    )
    op.create_index("ix_patient_access_grants_tenant_id", "patient_access_grants", ["tenant_id"])
    op.create_index(
        "ix_patient_access_grants_patient_actor_id", "patient_access_grants", ["patient_actor_id"]
    )
    op.create_index(
        "ix_patient_access_grants_doctor_actor_id", "patient_access_grants", ["doctor_actor_id"]
    )
    op.create_index(
        "ix_patient_access_grants_doctor_active",
        "patient_access_grants",
        ["tenant_id", "doctor_actor_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_access_grants_doctor_active", table_name="patient_access_grants")
    op.drop_index("ix_patient_access_grants_doctor_actor_id", table_name="patient_access_grants")
    op.drop_index("ix_patient_access_grants_patient_actor_id", table_name="patient_access_grants")
    op.drop_index("ix_patient_access_grants_tenant_id", table_name="patient_access_grants")
    op.drop_table("patient_access_grants")
