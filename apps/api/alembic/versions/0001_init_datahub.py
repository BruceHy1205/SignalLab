"""init datahub tables + timescale hypertable

Revision ID: 0001
Revises:
Create Date: 2026-07-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("exchange", sa.String(4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "daily_bars",
        sa.Column("symbol", sa.String(12), primary_key=True),
        sa.Column("trade_date", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("qfq_factor", sa.Float(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_daily_bars_trade_date", "daily_bars", ["trade_date"])
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    # TimescaleDB hypertable(扩展不存在时跳过,保证纯 pg 也能跑)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
                CREATE EXTENSION IF NOT EXISTS timescaledb;
                PERFORM create_hypertable(
                    'daily_bars', 'trade_date',
                    if_not_exists => TRUE, migrate_data => TRUE
                );
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_index("ix_daily_bars_trade_date", table_name="daily_bars")
    op.drop_table("daily_bars")
    op.drop_table("instruments")
