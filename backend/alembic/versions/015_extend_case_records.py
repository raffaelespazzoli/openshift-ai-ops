"""015_extend_case_records

Extend case_records table with incident linkage, structured diagnosis/plan/outcome
JSONB columns, and fast-path eligibility flag (Story 4.1, AD-20).

All new columns are NULLable for backward compatibility with the empty table
created by migration 005.

Revision ID: 015
Revises: 014
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE case_records "
        "ADD COLUMN incident_id UUID UNIQUE REFERENCES incidents(id)"
    )
    op.execute(
        "ALTER TABLE case_records ADD COLUMN diagnosis_object JSONB"
    )
    op.execute(
        "ALTER TABLE case_records ADD COLUMN remediation_plan JSONB"
    )
    op.execute(
        "ALTER TABLE case_records ADD COLUMN outcome_details JSONB"
    )
    op.execute(
        "ALTER TABLE case_records "
        "ADD COLUMN fast_path_eligible BOOLEAN DEFAULT TRUE"
    )

    op.execute(
        "CREATE INDEX idx_case_records_fast_path "
        "ON case_records(fast_path_eligible) WHERE fast_path_eligible = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_case_records_fast_path")
    op.execute("ALTER TABLE case_records DROP COLUMN IF EXISTS fast_path_eligible")
    op.execute("ALTER TABLE case_records DROP COLUMN IF EXISTS outcome_details")
    op.execute("ALTER TABLE case_records DROP COLUMN IF EXISTS remediation_plan")
    op.execute("ALTER TABLE case_records DROP COLUMN IF EXISTS diagnosis_object")
    op.execute("ALTER TABLE case_records DROP COLUMN IF EXISTS incident_id")
