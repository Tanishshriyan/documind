"""track Gemini embedding provenance

Revision ID: 0005_embedding_provenance
Revises: 0004_document_ownership
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_embedding_provenance"
down_revision = "0004_document_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    op.execute("UPDATE documents SET status = 'needs_reindex' WHERE status = 'ready'")


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding_dimension")
    op.drop_column("document_chunks", "embedding_model")

