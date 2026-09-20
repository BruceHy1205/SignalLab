"""datahub 表的读写。upsert 幂等(PK 冲突则更新),同步任务可安全重跑。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from signal_datahub.models import DailyBar, Instrument, SyncRun, utcnow


def _upsert(session: Session, table, rows: list[dict], index_elements: list[str]) -> int:
    """方言感知 upsert:PostgreSQL 与 SQLite(测试)都支持 ON CONFLICT。"""
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise NotImplementedError(f"不支持的方言: {dialect}")
    stmt = insert(table).values(rows)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in table.__table__.columns
        if c.name not in index_elements
    }
    session.execute(stmt.on_conflict_do_update(index_elements=index_elements, set_=update_cols))
    return len(rows)


def upsert_instruments(session: Session, df: pd.DataFrame) -> int:
    rows = [
        {
            "symbol": r["symbol"],
            "name": r["name"],
            "exchange": r["exchange"],
            "aliases": [],
            "status": "active",
            "updated_at": utcnow(),
        }
        for r in df.to_dict("records")
    ]
    return _upsert(session, Instrument, rows, ["symbol"])


def upsert_daily_bars(session: Session, symbol: str, df: pd.DataFrame, source: str) -> int:
    rows = [
        {
            "symbol": symbol,
            "trade_date": r["trade_date"],
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r["volume"]),
            "amount": float(r["amount"]),
            "qfq_factor": float(r["qfq_factor"]),
            "source": source,
            "updated_at": utcnow(),
        }
        for r in df.to_dict("records")
    ]
    return _upsert(session, DailyBar, rows, ["symbol", "trade_date"])


def last_trade_date(session: Session, symbol: str) -> date | None:
    return session.execute(
        select(func.max(DailyBar.trade_date)).where(DailyBar.symbol == symbol)
    ).scalar()


def get_bar(session: Session, symbol: str, trade_date: date) -> DailyBar | None:
    return session.execute(
        select(DailyBar).where(DailyBar.symbol == symbol, DailyBar.trade_date == trade_date)
    ).scalar_one_or_none()


def get_bars(session: Session, symbol: str, start: date, end: date) -> Sequence[DailyBar]:
    return (
        session.execute(
            select(DailyBar)
            .where(DailyBar.symbol == symbol, DailyBar.trade_date.between(start, end))
            .order_by(DailyBar.trade_date)
        )
        .scalars()
        .all()
    )


def search_instruments(session: Session, query: str, limit: int = 20) -> Sequence[Instrument]:
    q = f"%{query}%"
    return (
        session.execute(
            select(Instrument)
            .where(Instrument.symbol.like(q) | Instrument.name.like(q))
            .limit(limit)
        )
        .scalars()
        .all()
    )


def list_symbols_with_bars(
    session: Session,
    *,
    symbols: Sequence[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[str]:
    """有日线的标的列表(可按区间过滤)。"""
    stmt = select(DailyBar.symbol).distinct()
    if symbols:
        stmt = stmt.where(DailyBar.symbol.in_(list(symbols)))
    if start is not None:
        stmt = stmt.where(DailyBar.trade_date >= start)
    if end is not None:
        stmt = stmt.where(DailyBar.trade_date <= end)
    stmt = stmt.order_by(DailyBar.symbol)
    return list(session.execute(stmt).scalars().all())


def list_trade_dates(
    session: Session,
    *,
    symbols: Sequence[str] | None = None,
    start: date | None = None,
    end: date | None = None,
) -> list[date]:
    """交易日并集(升序),用作 Qlib calendars/day.txt。"""
    stmt = select(DailyBar.trade_date).distinct()
    if symbols:
        stmt = stmt.where(DailyBar.symbol.in_(list(symbols)))
    if start is not None:
        stmt = stmt.where(DailyBar.trade_date >= start)
    if end is not None:
        stmt = stmt.where(DailyBar.trade_date <= end)
    stmt = stmt.order_by(DailyBar.trade_date)
    return list(session.execute(stmt).scalars().all())


def start_sync_run(session: Session, job_type: str, detail: dict) -> SyncRun:
    run = SyncRun(job_type=job_type, detail=detail)
    session.add(run)
    session.flush()
    return run


def finish_sync_run(session: Session, run: SyncRun, status: str, detail: dict) -> None:
    run.status = status
    run.finished_at = utcnow()
    run.detail = {**run.detail, **detail}


def recent_sync_runs(session: Session, limit: int = 20) -> Sequence[SyncRun]:
    return (
        session.execute(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(limit))
        .scalars()
        .all()
    )
