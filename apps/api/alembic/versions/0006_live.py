"""live_intents

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("symbol", sa.String(12), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("signal_id", sa.String(36), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("broker", sa.String(32), nullable=False),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_live_intents_symbol", "live_intents", ["symbol"])
    op.create_index("ix_live_intents_status", "live_intents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_live_intents_status", table_name="live_intents")
    op.drop_index("ix_live_intents_symbol", table_name="live_intents")
    op.drop_table("live_intents")
