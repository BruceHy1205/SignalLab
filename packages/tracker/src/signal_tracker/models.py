"""tracker 拥有的表。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON, list: JSON}


class Source(Base):
    """机构/老师。"""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(64), unique=True)
    channel: Mapped[str] = mapped_column(String(32), default="wechat")  # wechat / paste / other
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    """一条结构化推荐。"""

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id"), index=True)
    message_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)  # 消歧后
    symbol_name: Mapped[str] = mapped_column(String(64))  # LLM 抽出的名称
    action: Mapped[str] = mapped_column(String(16))  # buy / sell / hold / watch
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizon: Mapped[str] = mapped_column(String(16), default="short")  # short/mid/long
    confidence: Mapped[str] = mapped_column(String(16))  # explicit / mention / review
    reason: Mapped[str] = mapped_column(Text, default="")
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending(待消歧)/active/ignored
    # 基准价锚定结果
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_rule: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # close_same_day / open_next_day
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_rec_source_time", "source_id", "message_time"),)


class RecPerformance(Base):
    """event study 结果,按窗口一行。"""

    __tablename__ = "rec_performance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendations.id"), index=True
    )
    window_days: Mapped[int] = mapped_column(Integer)  # 1/3/5/10/20/60
    abs_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_return: Mapped[float | None] = mapped_column(Float, nullable=True)  # vs 沪深300
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_runup: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_target_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hit_stop_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 计算所用最后交易日
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("uq_rec_perf_window", "recommendation_id", "window_days", unique=True),)
