"""实盘意图表:人工确认后才提交 broker。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON}


class LiveIntent(Base):
    __tablename__ = "live_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    side: Mapped[str] = mapped_column(String(8))  # buy / sell
    quantity: Mapped[int] = mapped_column(Integer)
    # pending_confirm → confirmed|rejected|cancelled ; confirmed → submitted|failed
    status: Mapped[str] = mapped_column(String(24), default="pending_confirm", index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual / agent / api
    signal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    broker: Mapped[str] = mapped_column(String(32), default="stub")
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
