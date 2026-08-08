"""002_correlation_tables

Add correlation_groups and alert_group_members tables.
Add fingerprint index on alerts for dedup performance.
Add root_cause_event_id to incidents (nullable FK set on sealing).

Revision ID: 002
Revises: 001
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "correlation_groups",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="open"),
        sa.Column("settling_window_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_age_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_evidence", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    op.create_table(
        "alert_group_members",
        sa.Column("group_id", sa.UUID(), sa.ForeignKey("correlation_groups.id"), nullable=False),
        sa.Column("alert_id", sa.UUID(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("incident_id", sa.UUID(), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("group_id", "alert_id"),
    )

    op.create_index("ix_alerts_fingerprint", "alerts", ["fingerprint"])

    op.add_column(
        "incidents",
        sa.Column("root_cause_event_id", sa.UUID(), sa.ForeignKey("correlation_groups.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("incidents", "root_cause_event_id")
    op.drop_index("ix_alerts_fingerprint", table_name="alerts")
    op.drop_table("alert_group_members")
    op.drop_table("correlation_groups")
