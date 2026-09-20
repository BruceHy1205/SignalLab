"""tracker tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("message_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=True),
        sa.Column("symbol_name", sa.String(64), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("baseline_date", sa.Date(), nullable=True),
        sa.Column("baseline_price", sa.Float(), nullable=True),
        sa.Column("baseline_rule", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recommendations_source_id", "recommendations", ["source_id"])
    op.create_index("ix_recommendations_message_time", "recommendations", ["message_time"])
    op.create_index("ix_recommendations_symbol", "recommendations", ["symbol"])
    op.create_index("ix_rec_source_time", "recommendations", ["source_id", "message_time"])
    op.create_table(
        "rec_performance",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.String(36),
            sa.ForeignKey("recommendations.id"),
            nullable=False,
        ),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("abs_return", sa.Float(), nullable=True),
        sa.Column("excess_return", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("max_runup", sa.Float(), nullable=True),
        sa.Column("hit_target_first", sa.Boolean(), nullable=True),
        sa.Column("hit_stop_first", sa.Boolean(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rec_performance_recommendation_id", "rec_performance", ["recommendation_id"]
    )
    op.create_index(
        "uq_rec_perf_window",
        "rec_performance",
        ["recommendation_id", "window_days"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_rec_perf_window", table_name="rec_performance")
    op.drop_index("ix_rec_performance_recommendation_id", table_name="rec_performance")
    op.drop_table("rec_performance")
    op.drop_index("ix_rec_source_time", table_name="recommendations")
    op.drop_index("ix_recommendations_symbol", table_name="recommendations")
    op.drop_index("ix_recommendations_message_time", table_name="recommendations")
    op.drop_index("ix_recommendations_source_id", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_table("sources")
