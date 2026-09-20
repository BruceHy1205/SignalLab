"""把 datahub 包一层,实现 tracker.ports.BarsReader。

此模块在 apps/api(组装层),是唯一允许同时 import datahub 与 tracker 的地方。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from signal_datahub.models import DailyBar, Instrument
from sqlalchemy import select


class DatahubBarsReader:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(DailyBar)
                    .where(
                        DailyBar.symbol == symbol,
                        DailyBar.trade_date.between(start, end),
                    )
                    .order_by(DailyBar.trade_date)
                )
                .scalars()
                .all()
            )
        if not rows:
            return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close"])
        return pd.DataFrame(
            [
                {
                    "trade_date": r.trade_date,
                    "open": float(r.open) * r.qfq_factor,
                    "high": float(r.high) * r.qfq_factor,
                    "low": float(r.low) * r.qfq_factor,
                    "close": float(r.close) * r.qfq_factor,
                }
                for r in rows
            ]
        )

    def resolve_symbol(self, name: str) -> list[tuple[str, str]]:
        with self._session_factory() as session:
            q = f"%{name}%"
            rows = (
                session.execute(
                    select(Instrument).where(Instrument.name.like(q) | Instrument.symbol.like(q))
                )
                .scalars()
                .all()
            )
        return [(r.symbol, r.name) for r in rows]

    def list_aliases(self) -> dict[str, str]:
        with self._session_factory() as session:
            rows = session.execute(select(Instrument)).scalars().all()
        out: dict[str, str] = {}
        for r in rows:
            out[r.name] = r.symbol
            for a in r.aliases or []:
                out[str(a)] = r.symbol
        return out
