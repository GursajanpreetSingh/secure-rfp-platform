"""embeddings are 384 numbers (local bge-small model)

Revision ID: 8d2e4f6a1b3c
Revises: 7cf310614897
"""

from alembic import op

revision = "8d2e4f6a1b3c"
down_revision = "7cf310614897"
branch_labels = None
depends_on = None


def _resize(dimension: int) -> None:
    # An index cannot be kept while the column type changes, so it is dropped and rebuilt.
    # Embeddings of the old size are meaningless for the new model, so they are cleared.
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("UPDATE chunks SET embedding = NULL")
    op.execute(
        f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({dimension}) "
        f"USING NULL::vector({dimension})"
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def upgrade() -> None:
    _resize(384)


def downgrade() -> None:
    _resize(1536)
