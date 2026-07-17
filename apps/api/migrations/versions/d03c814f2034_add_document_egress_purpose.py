"""Allow PHI-free external document-parse egress decisions.

Revision ID: d03c814f2034
Revises: c03c814f2033
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d03c814f2034"
down_revision: str | Sequence[str] | None = "c03c814f2033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_provider_egress_purpose", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_purpose",
        "provider_egress_events",
        "purpose IN ('external_search_query','external_tts','external_asr_audio','external_document_parse')",
    )
    op.drop_constraint("valid_provider_egress_processor", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_processor",
        "provider_egress_events",
        "processor IN ('mimo_tts','mimo_asr','mineru','anysearch','tavily')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_provider_egress_processor", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_processor",
        "provider_egress_events",
        "processor IN ('mimo_tts','mimo_asr','anysearch','tavily')",
    )
    op.drop_constraint("valid_provider_egress_purpose", "provider_egress_events", type_="check")
    op.create_check_constraint(
        "valid_provider_egress_purpose",
        "provider_egress_events",
        "purpose IN ('external_search_query','external_tts','external_asr_audio')",
    )
