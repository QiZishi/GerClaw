"""add encrypted versioned Skill registry and session selections

Revision ID: c29c814f2018
Revises: e41b8c2a2017
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c29c814f2018"
down_revision: str | None = "e41b8c2a2017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column(
            "parameter_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_markdown", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
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
            "origin IN ('text','upload','generated')",
            name=op.f("ck_skill_definitions_valid_origin"),
        ),
        sa.CheckConstraint(
            "revision > 0",
            name=op.f("ck_skill_definitions_positive_revision"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_definitions")),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "skill_id",
            name="uq_skill_definitions_owner_skill",
        ),
    )
    op.create_index(
        op.f("ix_skill_definitions_tenant_id"),
        "skill_definitions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_skill_definitions_actor_id"),
        "skill_definitions",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_definitions_owner_updated",
        "skill_definitions",
        ["tenant_id", "actor_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "skill_definition_revisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("skill_definition_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0",
            name=op.f("ck_skill_definition_revisions_positive_revision"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_definition_id"],
            ["skill_definitions.id"],
            name=op.f("fk_skill_definition_revisions_skill_definition_id_skill_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_definition_revisions")),
        sa.UniqueConstraint(
            "skill_definition_id",
            "revision",
            name="uq_skill_definition_revisions_record_revision",
        ),
    )
    op.create_index(
        op.f("ix_skill_definition_revisions_tenant_id"),
        "skill_definition_revisions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_skill_definition_revisions_actor_id"),
        "skill_definition_revisions",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_definition_revisions_owner_created",
        "skill_definition_revisions",
        ["tenant_id", "actor_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "session_skills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0 AND position < 10",
            name=op.f("ck_session_skills_valid_position"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_session_skills_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_skills")),
        sa.UniqueConstraint(
            "tenant_id",
            "session_id",
            "position",
            name="uq_session_skills_session_position",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "session_id",
            "skill_id",
            name="uq_session_skills_session_skill",
        ),
    )
    op.create_index(
        op.f("ix_session_skills_tenant_id"),
        "session_skills",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_session_skills_actor_id"),
        "session_skills",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        "ix_session_skills_owner_session",
        "session_skills",
        ["tenant_id", "actor_id", "session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_session_skills_owner_session", table_name="session_skills")
    op.drop_index(op.f("ix_session_skills_actor_id"), table_name="session_skills")
    op.drop_index(op.f("ix_session_skills_tenant_id"), table_name="session_skills")
    op.drop_table("session_skills")
    op.drop_index(
        "ix_skill_definition_revisions_owner_created",
        table_name="skill_definition_revisions",
    )
    op.drop_index(
        op.f("ix_skill_definition_revisions_actor_id"),
        table_name="skill_definition_revisions",
    )
    op.drop_index(
        op.f("ix_skill_definition_revisions_tenant_id"),
        table_name="skill_definition_revisions",
    )
    op.drop_table("skill_definition_revisions")
    op.drop_index("ix_skill_definitions_owner_updated", table_name="skill_definitions")
    op.drop_index(op.f("ix_skill_definitions_actor_id"), table_name="skill_definitions")
    op.drop_index(op.f("ix_skill_definitions_tenant_id"), table_name="skill_definitions")
    op.drop_table("skill_definitions")
