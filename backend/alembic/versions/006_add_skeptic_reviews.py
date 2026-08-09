"""006_add_skeptic_reviews

Add skeptic_reviews table for adversarial diagnosis validation
audit trail (AD-25, Story 2.4).

Revision ID: 006
Revises: 005
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE skeptic_reviews (
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
        CREATE INDEX idx_skeptic_reviews_incident ON skeptic_reviews(incident_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_skeptic_reviews_incident")
    op.execute("DROP TABLE IF EXISTS skeptic_reviews")
