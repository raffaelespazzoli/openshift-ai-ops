"""016_add_learning_store_config

Add learning_store_config table for runtime config overrides (Story 4.2, AD-7).

Revision ID: 016
Revises: 015
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE learning_store_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            updated_by TEXT DEFAULT ''
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS learning_store_config")
