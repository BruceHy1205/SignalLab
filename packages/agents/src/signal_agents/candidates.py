"""候选池 + 技术指标快照(规则决策与 LLM prompt 共用)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from signal_agents.ports import MarketPort, TrackerPort, WatchlistPort

CN = ZoneInfo("Asia/Shanghai")


@dataclass
class CandidateSnapshot:
    symbol: str
    close: float
    ret_5d: float | None
    ret_20d: float | None
    ma5: float | None
    ma20: float | None
    rec_stats: dict
    above_ma20: bool | None


def build_candidate_pool(
    watchlist: WatchlistPort,
    tracker: TrackerPort,
    extra: list[str] | None = None,
    limit: int = 20,
) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for s in (
        list(watchlist.list_symbols())
        + tracker.recent_recommended_symbols(30, limit)
        + (extra or [])
    ):
        if s and s not in seen:
            seen.add(s)
            symbols.append(s)
        if len(symbols) >= limit:
            break
    return symbols


def _market_today() -> date:
    return datetime.now(CN).date()


def snapshot_symbol(
    market: MarketPort, tracker: TrackerPort, symbol: str
) -> CandidateSnapshot | None:
    end = _market_today()
    start = end - timedelta(days=60)
    bars = market.get_qfq_bars(symbol, start, end)
    if bars is None or bars.empty or len(bars) < 6:
        return None
    closes = bars["close"].astype(float)
    close = float(closes.iloc[-1])
    ret_5d = float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1 if len(closes) >= 6 else None
    ret_20d = float(closes.iloc[-1]) / float(closes.iloc[-21]) - 1 if len(closes) >= 21 else None
    ma5 = float(closes.tail(5).to_numpy().mean()) if len(closes) >= 5 else None
    ma20 = float(closes.tail(20).to_numpy().mean()) if len(closes) >= 20 else None
    stats = tracker.rec_stats_for_symbol(symbol, window_days=5)
    above = (close > ma20) if ma20 else None
    return CandidateSnapshot(
        symbol=symbol,
        close=close,
        ret_5d=ret_5d,
        ret_20d=ret_20d,
        ma5=ma5,
        ma20=ma20,
        rec_stats=stats,
        above_ma20=above,
    )


def momentum_score(snap: CandidateSnapshot) -> float:
    """简单动量分:-1~1。"""
    score = 0.0
    if snap.ret_5d is not None:
        score += max(min(snap.ret_5d * 5, 0.5), -0.5)
    if snap.above_ma20:
        score += 0.2
    elif snap.above_ma20 is False:
        score -= 0.2
    win = snap.rec_stats.get("win_rate")
    if isinstance(win, (int, float)):
        score += (float(win) - 0.5) * 0.4
    return max(min(score, 1.0), -1.0)
