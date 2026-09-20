"""datahub 拥有的表。daily_bars 存原始价格 + qfq_factor,前复权价在读取时计算。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON, list: JSON}


class Instrument(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(12), primary_key=True)  # 600519.SH
    name: Mapped[str] = mapped_column(String(64))
    aliases: Mapped[list] = mapped_column(JSON, default=list)  # 常见口语别名,tracker 消歧用
    exchange: Mapped[str] = mapped_column(String(4))  # SH / SZ / BJ
    status: Mapped[str] = mapped_column(String(16), default="active")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyBar(Base):
    __tablename__ = "daily_bars"

    symbol: Mapped[str] = mapped_column(String(12), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Numeric(12, 4))
    high: Mapped[float] = mapped_column(Numeric(12, 4))
    low: Mapped[float] = mapped_column(Numeric(12, 4))
    close: Mapped[float] = mapped_column(Numeric(12, 4))
    volume: Mapped[int] = mapped_column(BigInteger)  # 手
    amount: Mapped[float] = mapped_column(Numeric(20, 2))  # 元
    qfq_factor: Mapped[float] = mapped_column(Float, default=1.0)  # 前复权价 = 原始价 * qfq_factor
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_daily_bars_trade_date", "trade_date"),)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type: Mapped[str] = mapped_column(String(32))  # instruments / index_cons / daily_bars
    status: Mapped[str] = mapped_column(
        String(16), default="running"
    )  # running/succeeded/partial/failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 参数、计数、失败清单
