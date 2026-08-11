"""009_nullable_queue_item_id

Make active_pipelines.queue_item_id nullable so remediation tasks
(which are not queue-driven) can register without a synthetic queue row.

Revision ID: 009
Revises: 008
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "active_pipelines",
        "queue_item_id",
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM active_pipelines WHERE queue_item_id IS NULL")
    op.alter_column(
        "active_pipelines",
        "queue_item_id",
        nullable=False,
    )
