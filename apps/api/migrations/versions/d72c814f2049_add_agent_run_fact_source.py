"""Add durable Agent run, event, answer, artifact, and feedback fact source.

Revision ID: d72c814f2049
Revises: c62c814f2048
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from gerclaw_api.encryption import EncryptedJSON, EncryptedText

revision: str = "d72c814f2049"
down_revision: str | None = "c62c814f2048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("input_message_id", sa.UUID(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("route", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("context_snapshot", EncryptedJSON(), nullable=False),
        sa.Column("plan", EncryptedJSON(), nullable=False),
        sa.Column("warnings", EncryptedJSON(), nullable=False),
        sa.Column("current_answer_version_id", sa.UUID(), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN "
            "('running','waiting_for_user','completed','completed_with_warnings',"
            "'failed','cancelled','interrupted')",
            name="valid_agent_run_status",
        ),
        sa.CheckConstraint(
            "((status IN ('completed','completed_with_warnings','failed','cancelled','interrupted') "
            "AND completed_at IS NOT NULL) OR "
            "(status IN ('running','waiting_for_user') AND completed_at IS NULL))",
            name="valid_agent_run_terminal_time",
        ),
        sa.CheckConstraint("route IN ('quick','standard','deep','emergency')", name="valid_route"),
        sa.CheckConstraint("revision > 0", name="positive_agent_run_revision"),
        sa.CheckConstraint("last_sequence >= 0", name="nonnegative_agent_run_sequence"),
        sa.CheckConstraint("fencing_token > 0", name="positive_agent_run_fence"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["input_message_id"], ["messages.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "trace_id", name="uq_agent_runs_tenant_trace"),
    )
    op.create_index("ix_agent_runs_tenant_id", "agent_runs", ["tenant_id"], unique=False)
    op.create_index("ix_agent_runs_actor_id", "agent_runs", ["actor_id"], unique=False)
    op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"], unique=False)
    op.create_index(
        "ix_agent_runs_owner_conversation_created",
        "agent_runs",
        ["tenant_id", "actor_id", "conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_status_updated",
        "agent_runs",
        ["status", "updated_at"],
        unique=False,
    )

    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=128), nullable=False),
        sa.Column("public_summary", EncryptedText(), nullable=True),
        sa.Column("payload", EncryptedJSON(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("sequence > 0", name="positive_run_event_sequence"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="nonnegative_run_event_duration",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
    )
    op.create_index(
        "ix_run_events_run_created",
        "run_events",
        ["run_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "answer_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("answer_group_id", sa.UUID(), nullable=False),
        sa.Column("assistant_message_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="positive_answer_version"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["messages.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"], ["answer_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "answer_group_id",
            "version",
            name="uq_answer_versions_group_version",
        ),
    )
    op.create_index("ix_answer_versions_run_id", "answer_versions", ["run_id"], unique=False)
    op.create_index(
        "uq_answer_versions_current_group",
        "answer_versions",
        ["run_id", "answer_group_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_foreign_key(
        "fk_agent_runs_current_answer_version",
        "agent_runs",
        "answer_versions",
        ["current_answer_version_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("title", EncryptedText(), nullable=False),
        sa.Column("markdown", EncryptedText(), nullable=False),
        sa.Column("kind", sa.String(length=32), server_default="markdown", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("saved", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('markdown','report','prescription','cga')",
            name="valid_run_artifact_kind",
        ),
        sa.CheckConstraint("revision > 0", name="positive_run_artifact_revision"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_run_artifacts_tenant_id", "run_artifacts", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_run_artifacts_actor_id", "run_artifacts", ["actor_id"], unique=False
    )
    op.create_index(
        "ix_run_artifacts_owner_conversation_updated",
        "run_artifacts",
        ["tenant_id", "actor_id", "conversation_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "run_feedback_states",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("value IN (-1,0,1)", name="valid_run_feedback_value"),
        sa.CheckConstraint("revision > 0", name="positive_run_feedback_revision"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "run_id",
            name="uq_run_feedback_states_owner_run",
        ),
    )
    op.create_index(
        "ix_run_feedback_states_tenant_id",
        "run_feedback_states",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_run_feedback_states_actor_id",
        "run_feedback_states",
        ["actor_id"],
        unique=False,
    )
    op.create_table(
        "run_feedback_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("feedback_state_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("value IN (-1,0,1)", name="valid_run_feedback_revision_value"),
        sa.CheckConstraint(
            "revision > 0", name="positive_run_feedback_revision_audit"
        ),
        sa.ForeignKeyConstraint(
            ["feedback_state_id"], ["run_feedback_states.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feedback_state_id",
            "revision",
            name="uq_run_feedback_revisions_state_revision",
        ),
    )


def downgrade() -> None:
    op.drop_table("run_feedback_revisions")
    op.drop_index("ix_run_feedback_states_actor_id", table_name="run_feedback_states")
    op.drop_index("ix_run_feedback_states_tenant_id", table_name="run_feedback_states")
    op.drop_table("run_feedback_states")
    op.drop_index(
        "ix_run_artifacts_owner_conversation_updated", table_name="run_artifacts"
    )
    op.drop_index("ix_run_artifacts_actor_id", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_tenant_id", table_name="run_artifacts")
    op.drop_table("run_artifacts")
    op.drop_constraint(
        "fk_agent_runs_current_answer_version",
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_index("uq_answer_versions_current_group", table_name="answer_versions")
    op.drop_index("ix_answer_versions_run_id", table_name="answer_versions")
    op.drop_table("answer_versions")
    op.drop_index("ix_run_events_run_created", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_agent_runs_status_updated", table_name="agent_runs")
    op.drop_index("ix_agent_runs_owner_conversation_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_trace_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_actor_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_tenant_id", table_name="agent_runs")
    op.drop_table("agent_runs")
