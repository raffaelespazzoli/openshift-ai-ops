"""005_add_case_records

Add case_records table with pgvector HNSW index for
Learning Store similarity queries (AD-20).

Table is created empty — Epic 4 populates it via the write path.

Revision ID: 005
Revises: 004
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE case_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_signature TEXT NOT NULL,
            alert_signature_embedding vector(1536),
            root_cause_code TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
            outcome_confidence FLOAT NOT NULL CHECK (outcome_confidence >= 0 AND outcome_confidence <= 1),
            ocp_version TEXT NOT NULL,
            cluster_context JSONB DEFAULT '{}',
            diagnosis_summary TEXT DEFAULT '',
            remediation_summary TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX case_records_embedding_idx
            ON case_records USING hnsw (alert_signature_embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS case_records_embedding_idx")
    op.execute("DROP TABLE IF EXISTS case_records")
