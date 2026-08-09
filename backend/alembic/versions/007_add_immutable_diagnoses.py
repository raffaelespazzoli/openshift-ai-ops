"""007_add_immutable_diagnoses

Add immutable_diagnoses table for sealed diagnosis artifacts
that cross the RBAC Airlock to the remediation side (AD-2, Story 2.4).

Epic 3's remediation planner reads from this table.

Revision ID: 007
Revises: 006
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE immutable_diagnoses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            diagnosis JSONB NOT NULL,
            skeptic_verdict JSONB NOT NULL,
            sealed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_immutable_diagnoses_incident ON immutable_diagnoses(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_immutable_diagnoses_incident")
    op.execute("DROP TABLE IF EXISTS immutable_diagnoses")
