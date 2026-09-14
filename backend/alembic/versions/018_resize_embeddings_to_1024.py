"""018_resize_embeddings_to_1024

Resize pgvector columns from text-embedding-3-small (1536) to
qwen3-embedding:0.6b (1024). Existing vectors cannot be recast, so they
are cleared and re-ingested on backend startup.

Revision ID: 018
Revises: 017
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RESIZE = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = '{table}'
      AND a.attname = '{column}'
      AND NOT a.attisdropped
      AND format_type(a.atttypid, a.atttypmod) = 'vector(1536)'
  ) THEN
    DROP INDEX IF EXISTS {index};
    ALTER TABLE {table}
      ALTER COLUMN {column} TYPE vector(1024) USING NULL::vector(1024);
    CREATE INDEX {index}
      ON {table} USING hnsw ({column} vector_cosine_ops);
  END IF;
END $$;
"""


def upgrade() -> None:
    op.execute(
        _RESIZE.format(
            table="runbook_chunks",
            column="embedding",
            index="runbook_chunks_embedding_idx",
        )
    )
    op.execute(
        _RESIZE.format(
            table="case_records",
            column="alert_signature_embedding",
            index="case_records_embedding_idx",
        )
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          DROP INDEX IF EXISTS runbook_chunks_embedding_idx;
          ALTER TABLE runbook_chunks
            ALTER COLUMN embedding TYPE vector(1536) USING NULL::vector(1536);
          CREATE INDEX runbook_chunks_embedding_idx
            ON runbook_chunks USING hnsw (embedding vector_cosine_ops);

          DROP INDEX IF EXISTS case_records_embedding_idx;
          ALTER TABLE case_records
            ALTER COLUMN alert_signature_embedding TYPE vector(1536)
            USING NULL::vector(1536);
          CREATE INDEX case_records_embedding_idx
            ON case_records USING hnsw (alert_signature_embedding vector_cosine_ops);
        END $$;
        """
    )
