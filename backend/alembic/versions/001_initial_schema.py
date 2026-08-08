"""001_initial_schema

Create application tables: incidents, alerts, audit_log.
Enable pgvector extension. DO NOT create langgraph_* tables (AD-3).

Revision ID: 001
Revises:
Create Date: 2026-08-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "incidents",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="received"),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", sa.UUID(), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("labels", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("annotations", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_resource", sa.String(255), nullable=True),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("alerts")
    op.drop_table("incidents")
    op.execute("DROP EXTENSION IF EXISTS vector")
