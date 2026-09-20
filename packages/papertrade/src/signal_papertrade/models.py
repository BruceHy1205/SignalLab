"""模拟盘表。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON, list: JSON}


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(64), unique=True)
    cash: Mapped[float] = mapped_column(Numeric(18, 2))
    initial_cash: Mapped[float] = mapped_column(Numeric(18, 2))
    # 费率配置
    commission_rate: Mapped[float] = mapped_column(Float, default=0.00025)  # 佣金率
    commission_min: Mapped[float] = mapped_column(Float, default=5.0)  # 最低佣金
    stamp_tax_rate: Mapped[float] = mapped_column(Float, default=0.0005)  # 印花税(卖出)
    slippage_bps: Mapped[float] = mapped_column(Float, default=5.0)  # 滑点(基点)
    lot_size: Mapped[int] = mapped_column(Integer, default=100)  # A 股整手
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    side: Mapped[str] = mapped_column(String(8))  # buy / sell
    quantity: Mapped[int] = mapped_column(Integer)  # 股
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending → filled | rejected | cancelled
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / agent / api
    note: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # 成交信息
    fill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fill_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (Index("ix_orders_acct_status", "account_id", "status"),)


class Position(Base):
    __tablename__ = "positions"

    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(12), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)  # 每股成本(含费摊薄)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NavPoint(Base):
    __tablename__ = "nav"

    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    cash: Mapped[float] = mapped_column(Numeric(18, 2))
    market_value: Mapped[float] = mapped_column(Numeric(18, 2))
    nav: Mapped[float] = mapped_column(Numeric(18, 2))  # cash + market_value
    bench_nav: Mapped[float | None] = mapped_column(Float, nullable=True)  # 沪深300归一化
