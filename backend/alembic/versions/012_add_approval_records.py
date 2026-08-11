"""012_add_approval_records

Add approval_records table for human approval workflow (Story 3.4).

Revision ID: 012
Revises: 011
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE approval_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            plan_id UUID NOT NULL REFERENCES remediation_plans(id),
            action TEXT NOT NULL CHECK (action IN ('approved', 'rejected')),
            actor TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_approval_records_incident
            ON approval_records(incident_id)
    """)

    op.execute("""
        CREATE TABLE policy_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            severity TEXT NOT NULL,
            blast_radius TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            new_auto_approve BOOLEAN NOT NULL,
            actor TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policy_adjustments")
    op.execute("DROP TABLE IF EXISTS approval_records")
