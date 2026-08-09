"""004_add_runbook_chunks

Add runbook_chunks table with pgvector HNSW index for
semantic similarity search over embedded runbook content (AD-13).

Revision ID: 004
Revises: 003
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE runbook_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_file TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            heading_hierarchy TEXT[] DEFAULT '{}',
            content TEXT NOT NULL,
            embedding vector(1536),
            token_count INTEGER NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(source_file, chunk_index)
        )
    """)

    op.execute("""
        CREATE INDEX runbook_chunks_embedding_idx
            ON runbook_chunks USING hnsw (embedding vector_cosine_ops)
    """)

    op.execute("""
        CREATE INDEX runbook_chunks_source_file_idx
            ON runbook_chunks (source_file)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS runbook_chunks_source_file_idx")
    op.execute("DROP INDEX IF EXISTS runbook_chunks_embedding_idx")
    op.execute("DROP TABLE IF EXISTS runbook_chunks")
