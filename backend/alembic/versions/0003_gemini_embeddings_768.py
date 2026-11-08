"""replace placeholder embeddings with Gemini Embedding 2 dimensions

Revision ID: 0003_gemini_embeddings_768
Revises: 0002_pgvector
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0003_gemini_embeddings_768"
down_revision = "0002_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "embedding")
    op.add_column("document_chunks", sa.Column("embedding", Vector(768), nullable=True))
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )
        op.execute("UPDATE documents SET status = 'needs_reindex' WHERE status = 'ready'")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "embedding")
    op.add_column("document_chunks", sa.Column("embedding", Vector(384), nullable=True))
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )

