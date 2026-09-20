"""papertrade tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("initial_cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("commission_rate", sa.Float(), nullable=False),
        sa.Column("commission_min", sa.Float(), nullable=False),
        sa.Column("stamp_tax_rate", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("symbol", sa.String(12), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fill_date", sa.Date(), nullable=True),
        sa.Column("fill_price", sa.Float(), nullable=True),
        sa.Column("fill_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("reject_reason", sa.String(128), nullable=True),
    )
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_acct_status", "orders", ["account_id", "status"])
    op.create_table(
        "positions",
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("symbol", sa.String(12), primary_key=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_cost", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "nav",
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("market_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("nav", sa.Numeric(18, 2), nullable=False),
        sa.Column("bench_nav", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("nav")
    op.drop_table("positions")
    op.drop_index("ix_orders_acct_status", table_name="orders")
    op.drop_index("ix_orders_symbol", table_name="orders")
    op.drop_index("ix_orders_account_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("accounts")
