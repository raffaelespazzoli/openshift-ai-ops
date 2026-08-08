"""003_priority_queue_tables

Add priority_queue and active_pipelines tables for
durable work queue and parallelism tracking (AD-23, NFR-2).

Revision ID: 003
Revises: 002
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "priority_queue",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("root_cause_event_id", sa.UUID(), sa.ForeignKey("correlation_groups.id"), nullable=False, unique=True),
        sa.Column("incident_id", sa.UUID(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("dequeued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_priority_queue_pending",
        "priority_queue",
        [sa.text("priority_score DESC"), sa.text("enqueued_at ASC")],
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_index(
        "idx_priority_queue_rce",
        "priority_queue",
        ["root_cause_event_id"],
    )

    op.create_table(
        "active_pipelines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("queue_item_id", sa.UUID(), sa.ForeignKey("priority_queue.id"), nullable=False),
        sa.Column("incident_id", sa.UUID(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("active_pipelines")
    op.drop_index("idx_priority_queue_rce", table_name="priority_queue")
    op.drop_index("idx_priority_queue_pending", table_name="priority_queue")
    op.drop_table("priority_queue")
