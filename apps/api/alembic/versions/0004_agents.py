"""agents tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("llm_cost_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("suggested_qty", sa.Integer(), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_signals_run_id", "signals", ["run_id"])
    op.create_index("ix_signals_symbol", "signals", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_signals_symbol", table_name="signals")
    op.drop_index("ix_signals_run_id", table_name="signals")
    op.drop_table("signals")
    op.drop_table("agent_runs")
