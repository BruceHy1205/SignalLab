"""agents 拥有的表。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON, list: JSON}


class AgentRun(Base):
    """一次候选池决策运行。"""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/succeeded/failed
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(64), default="")
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Signal(Base):
    """单只股票的决策信号 + 完整角色对话。"""

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    action: Mapped[str] = mapped_column(String(16))  # buy / sell / hold
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    suggested_qty: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[dict] = mapped_column(JSON, default=dict)  # 各角色发言 + 摘要
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
