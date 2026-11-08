"""add authenticated users

Revision ID: 0006_users
Revises: 0005_embedding_provenance
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_users"
down_revision = "0005_embedding_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.execute(
        """
        INSERT INTO users (id, email, display_name, password_hash, is_active, created_at, updated_at)
        SELECT owner_id,
               'legacy-' || md5(owner_id) || '@invalid.local',
               'Legacy workspace',
               '!disabled-legacy-user',
               FALSE,
               CURRENT_TIMESTAMP,
               CURRENT_TIMESTAMP
        FROM (
            SELECT owner_id FROM documents
            UNION
            SELECT owner_id FROM conversations
        ) AS legacy_owners
        WHERE owner_id IS NOT NULL
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.alter_column("documents", "owner_id", server_default=None)
    op.alter_column("conversations", "owner_id", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

