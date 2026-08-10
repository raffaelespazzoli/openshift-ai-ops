"""008_add_remediation_plans

Add remediation_plans table for storing structured remediation plans
produced by the planner agent (Story 3.1).

Revision ID: 008
Revises: 007
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE remediation_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            diagnosis_id UUID NOT NULL REFERENCES immutable_diagnoses(id),
            plan JSONB NOT NULL,
            blast_radius TEXT NOT NULL,
            estimated_risk TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_remediation_plans_incident ON remediation_plans(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_remediation_plans_incident")
    op.execute("DROP TABLE IF EXISTS remediation_plans")
