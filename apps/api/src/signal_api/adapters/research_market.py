"""组装层:research ↔ datahub。"""

from __future__ import annotations

from datetime import date

import pandas as pd
from signal_datahub.models import DailyBar, Instrument
from sqlalchemy import select


class ResearchMarketAdapter:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        with self._sf() as session:
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
            return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(
            [
                {
                    "trade_date": r.trade_date,
                    "open": float(r.open) * r.qfq_factor,
                    "high": float(r.high) * r.qfq_factor,
                    "low": float(r.low) * r.qfq_factor,
                    "close": float(r.close) * r.qfq_factor,
                    "volume": float(r.volume),
                }
                for r in rows
            ]
        )

    def list_universe_symbols(self, universe: str = "csi300", limit: int = 30) -> list[str]:
        # 简化:从 instruments 取前 N 只;真实 CSI300 成分同步后可替换
        with self._sf() as session:
            rows = (
                session.execute(
                    select(Instrument.symbol).where(Instrument.status == "active").limit(limit)
                )
                .scalars()
                .all()
            )
        if rows:
            return list(rows)
        # 无 instruments 时回退常见样本
        return ["600519.SH", "000001.SZ", "300750.SZ"][:limit]
