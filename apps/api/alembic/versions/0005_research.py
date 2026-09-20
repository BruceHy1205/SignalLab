"""research tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("producer", sa.String(32), nullable=False),
        sa.Column("scenario", sa.String(64), nullable=False),
        sa.Column("data_snapshot", sa.String(64), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("runtime", sa.JSON(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_loop", sa.Integer(), nullable=False),
        sa.Column("best_ic", sa.Float(), nullable=True),
        sa.Column("llm_cost_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_research_jobs_status", "research_jobs", ["status"])

    op.create_table(
        "research_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id"), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_events_job_id", "research_events", ["job_id"])
    op.create_index("uq_research_event_job_seq", "research_events", ["job_id", "seq"], unique=True)

    op.create_table(
        "strategies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("package_id", sa.String(36), nullable=False, unique=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id"), nullable=True),
        sa.Column("producer", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("universe", sa.String(32), nullable=False),
        sa.Column("data_snapshot", sa.String(64), nullable=False),
        sa.Column("signal_protocol", sa.String(32), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("verified_metrics", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "strategy_signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("trade_date", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_signals_strategy_id", "strategy_signals", ["strategy_id"])
    op.create_index(
        "uq_strategy_signal",
        "strategy_signals",
        ["strategy_id", "trade_date", "symbol"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_strategy_signal", table_name="strategy_signals")
    op.drop_index("ix_strategy_signals_strategy_id", table_name="strategy_signals")
    op.drop_table("strategy_signals")
    op.drop_table("strategies")
    op.drop_index("uq_research_event_job_seq", table_name="research_events")
    op.drop_index("ix_research_events_job_id", table_name="research_events")
    op.drop_table("research_events")
    op.drop_index("ix_research_jobs_status", table_name="research_jobs")
    op.drop_table("research_jobs")
