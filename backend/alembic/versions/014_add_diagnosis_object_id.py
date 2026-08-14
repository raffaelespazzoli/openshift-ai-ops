"""014_add_diagnosis_object_id

Add diagnosis_object_id column to immutable_diagnoses to preserve the
original DiagnosisObject UUID separately from the DB row PK.
This resolves the RBAC Airlock id-semantics decision (Epic 3 retro).

Revision ID: 014
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE immutable_diagnoses
        ADD COLUMN diagnosis_object_id UUID
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE immutable_diagnoses
        DROP COLUMN IF EXISTS diagnosis_object_id
    """)
