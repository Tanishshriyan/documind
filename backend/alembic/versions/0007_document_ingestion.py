"""add document ingestion lifecycle and storage metadata

Revision ID: 0007_document_ingestion
Revises: 0006_users
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_document_ingestion"
down_revision = "0006_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "documents",
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.add_column("documents", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=True))
    op.add_column("documents", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("documents", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("page_number_policy", sa.String(length=32), server_default="logical_document", nullable=True),
    )

    op.execute("UPDATE documents SET uploaded_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE uploaded_at IS NULL")
    op.execute(
        "UPDATE documents SET chunk_count = "
        "(SELECT COUNT(*) FROM document_chunks WHERE document_chunks.document_id = documents.id) "
        "WHERE chunk_count IS NULL"
    )
    op.execute("UPDATE documents SET page_number_policy = CASE WHEN content_type = 'application/pdf' THEN 'physical' ELSE 'logical_document' END")
    op.execute(
        "UPDATE documents SET status = CASE LOWER(status) "
        "WHEN 'ready' THEN 'READY' "
        "WHEN 'processing' THEN 'FAILED' "
        "WHEN 'error' THEN 'FAILED' "
        "WHEN 'needs_reindex' THEN 'FAILED' "
        "WHEN 'pending' THEN 'PENDING' "
        "WHEN 'failed' THEN 'FAILED' "
        "ELSE 'FAILED' END"
    )
    op.execute(
        "UPDATE documents SET failure_reason = 'Existing document embeddings require reindexing.' "
        "WHERE status = 'FAILED' AND failure_reason IS NULL"
    )
    op.alter_column("documents", "storage_path", nullable=True)
    op.alter_column("documents", "uploaded_at", nullable=False, server_default=None)
    op.alter_column("documents", "chunk_count", nullable=False, server_default=None)
    op.alter_column("documents", "page_number_policy", nullable=False, server_default=None)

    op.create_index(
        "uq_documents_owner_checksum",
        "documents",
        ["owner_id", "checksum_sha256"],
        unique=True,
        postgresql_where=sa.text("checksum_sha256 IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_owner_checksum", table_name="documents")
    for column in (
        "page_number_policy",
        "embedding_dimension",
        "embedding_model",
        "chunk_count",
        "failure_reason",
        "processing_completed_at",
        "processing_started_at",
        "uploaded_at",
        "checksum_sha256",
        "storage_key",
    ):
        op.drop_column("documents", column)
