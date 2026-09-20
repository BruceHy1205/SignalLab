"""research 表模型。

注意:agents 已占用 signals 表名;本包用 strategy_signals 存策略日信号。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON, list: JSON}


# provisioning → running → {succeeded|failed|budget_exceeded|lost}
JOB_STATUSES = (
    "draft",
    "provisioning",
    "running",
    "succeeded",
    "failed",
    "budget_exceeded",
    "lost",
)


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    producer: Mapped[str] = mapped_column(String(32), default="alphaagent")
    scenario: Mapped[str] = mapped_column(String(64), default="fin_factor")
    data_snapshot: Mapped[str] = mapped_column(String(64), default="")
    # 完整 ResearchJobSpec 的 dict 快照(创建后不可变)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    # 供给器运行时信息:container_id / work_dir 等
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_loop: Mapped[int] = mapped_column(Integer, default=0)
    best_ic: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    strategy_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvent(Base):
    __tablename__ = "research_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_jobs.id"), index=True)
    type: Mapped[str] = mapped_column(String(24))
    seq: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("uq_research_event_job_seq", "job_id", "seq", unique=True),)


class Strategy(Base):
    """已通过校验入库的策略包。"""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    package_id: Mapped[str] = mapped_column(String(36), unique=True)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_jobs.id"), nullable=True
    )
    producer: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128), default="")
    universe: Mapped[str] = mapped_column(String(32), default="csi300")
    data_snapshot: Mapped[str] = mapped_column(String(64), default="")
    signal_protocol: Mapped[str] = mapped_column(String(32))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    # 独立复算结果
    verified_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StrategySignal(Base):
    """策略产生的日信号(供模拟盘订阅)。"""

    __tablename__ = "strategy_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String(36), ForeignKey("strategies.id"), index=True)
    trade_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    symbol: Mapped[str] = mapped_column(String(12))
    score: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(8), default="hold")  # buy / sell / hold
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("uq_strategy_signal", "strategy_id", "trade_date", "symbol", unique=True),
    )
