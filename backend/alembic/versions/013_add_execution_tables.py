"""013_add_execution_tables

Add remediation_locks, execution_logs, outcome_results, rollback_records
tables for Story 3.5 (Serialized Execution, Outcome Observation & Rollback).

Revision ID: 013
Revises: 012
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE remediation_locks (
            id TEXT PRIMARY KEY DEFAULT 'global',
            locked_by UUID,
            locked_at TIMESTAMPTZ,
            incident_id UUID REFERENCES incidents(id)
        )
    """)
    op.execute("INSERT INTO remediation_locks (id) VALUES ('global')")

    op.execute("""
        CREATE TABLE execution_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            plan_id UUID NOT NULL REFERENCES remediation_plans(id),
            steps JSONB NOT NULL,
            mcp_calls JSONB,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_execution_logs_incident ON execution_logs(incident_id)
    """)

    op.execute("""
        CREATE TABLE outcome_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL UNIQUE REFERENCES incidents(id),
            alert_resolved BOOLEAN NOT NULL,
            resolution_method TEXT,
            resource_verification JSONB,
            outcome_confidence FLOAT NOT NULL,
            refire_detected BOOLEAN NOT NULL DEFAULT FALSE,
            observation_started_at TIMESTAMPTZ,
            observation_completed_at TIMESTAMPTZ,
            timeout_seconds INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_outcome_results_incident ON outcome_results(incident_id)
    """)

    op.execute("""
        CREATE TABLE rollback_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES incidents(id),
            plan_id UUID NOT NULL REFERENCES remediation_plans(id),
            actor TEXT NOT NULL,
            steps_executed JSONB,
            success BOOLEAN NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_rollback_records_incident ON rollback_records(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rollback_records")
    op.execute("DROP TABLE IF EXISTS outcome_results")
    op.execute("DROP TABLE IF EXISTS execution_logs")
    op.execute("DROP TABLE IF EXISTS remediation_locks")
