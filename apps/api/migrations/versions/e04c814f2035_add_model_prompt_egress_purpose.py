"""Allow PHI-free external model-prompt egress decisions.

Revision ID: e04c814f2035
Revises: d03c814f2034
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e04c814f2035"
down_revision: str | Sequence[str] | None = "d03c814f2034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_provider_egress_purpose", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_purpose",
        "provider_egress_events",
        "purpose IN ('external_search_query','external_tts','external_asr_audio','external_document_parse','external_model_prompt')",
    )
    op.drop_constraint("valid_provider_egress_processor", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_processor",
        "provider_egress_events",
        "processor IN ('mimo_tts','mimo_asr','mineru','anysearch','tavily','model_primary','model_backup1','model_backup2')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_provider_egress_processor", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_processor",
        "processor IN ('mimo_tts','mimo_asr','mineru','anysearch','tavily')",
    )
    op.drop_constraint("valid_provider_egress_purpose", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_purpose",
        "purpose IN ('external_search_query','external_tts','external_asr_audio','external_document_parse')",
    )
