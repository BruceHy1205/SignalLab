"""datahub → PriceReader 适配器(组装层)。"""

from __future__ import annotations

from datetime import date

from signal_datahub.models import DailyBar
from sqlalchemy import select


class DatahubPriceReader:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_open_close(self, symbol: str, trade_date: date) -> tuple[float, float] | None:
        with self._session_factory() as session:
            row = session.execute(
                select(DailyBar).where(DailyBar.symbol == symbol, DailyBar.trade_date == trade_date)
            ).scalar_one_or_none()
        if not row:
            return None
        return float(row.open), float(row.close)

    def get_prev_close(self, symbol: str, trade_date: date) -> float | None:
        with self._session_factory() as session:
            row = session.execute(
                select(DailyBar)
                .where(DailyBar.symbol == symbol, DailyBar.trade_date < trade_date)
                .order_by(DailyBar.trade_date.desc())
                .limit(1)
            ).scalar_one_or_none()
        return float(row.close) if row else None

    def list_trade_dates(self, start: date, end: date) -> list[date]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(DailyBar.trade_date)
                    .where(DailyBar.trade_date.between(start, end))
                    .distinct()
                    .order_by(DailyBar.trade_date)
                )
                .scalars()
                .all()
            )
        return list(rows)
