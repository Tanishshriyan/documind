"""scope documents and conversations to an owner

Revision ID: 0004_document_ownership
Revises: 0003_gemini_embeddings_768
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_document_ownership"
down_revision = "0003_gemini_embeddings_768"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("owner_id", sa.String(length=128), server_default="local-user", nullable=False))
    op.add_column("conversations", sa.Column("owner_id", sa.String(length=128), server_default="local-user", nullable=False))
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_owner_id", table_name="conversations")
    op.drop_index("ix_documents_owner_id", table_name="documents")
    op.drop_column("conversations", "owner_id")
    op.drop_column("documents", "owner_id")

