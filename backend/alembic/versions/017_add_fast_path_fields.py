"""017_add_fast_path_fields

Add fast_path, fast_path_similarity, fast_path_case_record_id to incidents table (Story 4.3).

Revision ID: 017
Revises: 016
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE incidents ADD COLUMN fast_path BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE incidents ADD COLUMN fast_path_similarity FLOAT")
    op.execute(
        "ALTER TABLE incidents ADD COLUMN fast_path_case_record_id UUID "
        "REFERENCES case_records(id)"
    )
    op.execute(
        "CREATE INDEX idx_incidents_fast_path ON incidents(fast_path) "
        "WHERE fast_path = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_incidents_fast_path")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS fast_path_case_record_id")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS fast_path_similarity")
    op.execute("ALTER TABLE incidents DROP COLUMN IF EXISTS fast_path")
