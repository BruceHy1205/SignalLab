"""组装层适配器:把 datahub/tracker/papertrade 接到 agents 端口。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from signal_datahub.models import DailyBar, Instrument
from signal_papertrade import repo as paper_repo
from signal_papertrade.service import PaperService
from signal_tracker.models import Recommendation, RecPerformance, Source
from sqlalchemy import select

CN = ZoneInfo("Asia/Shanghai")


class CompositeMarketPort:
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

    def resolve_name(self, name: str) -> list[tuple[str, str]]:
        with self._sf() as session:
            q = f"%{name}%"
            rows = (
                session.execute(select(Instrument).where(Instrument.name.like(q))).scalars().all()
            )
        return [(r.symbol, r.name) for r in rows]


class CompositeTrackerPort:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def recent_recommended_symbols(self, days: int = 30, limit: int = 50) -> list[str]:
        since = datetime.now(CN) - timedelta(days=days)
        with self._sf() as session:
            rows = (
                session.execute(
                    select(Recommendation.symbol)
                    .where(
                        Recommendation.status == "active",
                        Recommendation.confidence == "explicit",
                        Recommendation.symbol.is_not(None),
                        Recommendation.message_time >= since,
                    )
                    .order_by(Recommendation.message_time.desc())
                    .limit(limit * 3)
                )
                .scalars()
                .all()
            )
        out: list[str] = []
        seen: set[str] = set()
        for s in rows:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
            if len(out) >= limit:
                break
        return out

    def rec_stats_for_symbol(self, symbol: str, window_days: int = 5) -> dict:
        with self._sf() as session:
            q = (
                select(
                    Recommendation.action,
                    RecPerformance.abs_return,
                    RecPerformance.excess_return,
                    Source.name,
                )
                .join(Recommendation, Recommendation.id == RecPerformance.recommendation_id)
                .join(Source, Source.id == Recommendation.source_id)
                .where(
                    Recommendation.symbol == symbol,
                    Recommendation.confidence == "explicit",
                    Recommendation.status == "active",
                    Recommendation.action.in_(("buy", "sell")),
                    RecPerformance.window_days == window_days,
                    RecPerformance.abs_return.is_not(None),
                )
            )
            rows = session.execute(q).all()
        if not rows:
            return {"n": 0}
        n = len(rows)
        wins = 0
        signed_excesses: list[float] = []
        sources = sorted({r[3] for r in rows})
        for action, abs_r, excess, _ in rows:
            signed = float(abs_r) if action == "buy" else -float(abs_r)
            if signed > 0:
                wins += 1
            if excess is not None:
                signed_excesses.append(float(excess) if action == "buy" else -float(excess))
        return {
            "n": n,
            "win_rate": round(wins / n, 3),
            "avg_excess": (
                round(sum(signed_excesses) / len(signed_excesses), 4) if signed_excesses else None
            ),
            "sources": sources,
        }


class CompositePaperPort:
    def __init__(self, session_factory, paper_service: PaperService) -> None:
        self._sf = session_factory
        self._paper = paper_service

    def list_positions(self, account_id: str) -> list[dict]:
        with self._sf() as session:
            return [
                {"symbol": p.symbol, "quantity": p.quantity, "avg_cost": p.avg_cost}
                for p in paper_repo.list_positions(session, account_id)
            ]

    def place_order(
        self, account_id: str, symbol: str, side: str, quantity: int, note: str = ""
    ) -> dict:
        with self._sf() as session:
            order = self._paper.place_order(
                session, account_id, symbol, side, quantity, source="agent", note=note
            )
            return {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "status": order.status,
            }


class ConfigWatchlist:
    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or []

    def list_symbols(self) -> list[str]:
        return list(self._symbols)
