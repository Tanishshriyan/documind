"""persist per-message document selection scope

Revision ID: 0008_message_document_scope
Revises: 0007_document_ingestion
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_message_document_scope"
down_revision = "0007_document_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("selected_document_ids_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "selected_document_ids_json")
