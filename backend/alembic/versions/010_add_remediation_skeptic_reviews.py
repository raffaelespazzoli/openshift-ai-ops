"""010_add_remediation_skeptic_reviews

Add remediation_skeptic_reviews table for storing adversarial
challenge/response rounds from the Remediation Skeptic (Story 3.2).

Revision ID: 010
Revises: 009
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE remediation_skeptic_reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID NOT NULL REFERENCES incidents(id),
            round_number INTEGER NOT NULL,
            challenge JSONB NOT NULL,
            response JSONB NOT NULL,
            verdict JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(incident_id, round_number)
        )
    """)

    op.execute("""
        CREATE INDEX idx_remediation_skeptic_reviews_incident
            ON remediation_skeptic_reviews(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_remediation_skeptic_reviews_incident")
    op.execute("DROP TABLE IF EXISTS remediation_skeptic_reviews")
