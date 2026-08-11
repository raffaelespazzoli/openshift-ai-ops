"""011_add_dry_run_and_policy_gate

Add dry_run_results and policy_decisions tables for
pre-flight validation and policy gate evaluation (Story 3.3).

Revision ID: 011
Revises: 010
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dry_run_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            plan_id UUID NOT NULL REFERENCES remediation_plans(id),
            step_results JSONB NOT NULL,
            dry_run_passed BOOLEAN NOT NULL,
            dry_run_errors JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_dry_run_results_incident
            ON dry_run_results(incident_id)
    """)

    op.execute("""
        CREATE TABLE policy_decisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            plan_id UUID NOT NULL REFERENCES remediation_plans(id),
            dimensions JSONB NOT NULL,
            evidence_complete BOOLEAN NOT NULL,
            evidence_gaps_empty BOOLEAN NOT NULL,
            auto_execution_approved BOOLEAN NOT NULL,
            reasoning TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_policy_decisions_incident
            ON policy_decisions(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policy_decisions")
    op.execute("DROP TABLE IF EXISTS dry_run_results")
