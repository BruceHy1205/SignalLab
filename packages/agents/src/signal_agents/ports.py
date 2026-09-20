"""agents 对外依赖的端口(组装层注入实现)。"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd


class MarketPort(Protocol):
    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """列:trade_date, open, high, low, close。"""
        ...

    def resolve_name(self, name: str) -> list[tuple[str, str]]: ...


class TrackerPort(Protocol):
    def recent_recommended_symbols(self, days: int = 30, limit: int = 50) -> list[str]: ...

    def rec_stats_for_symbol(self, symbol: str, window_days: int = 5) -> dict:
        """返回该票近期推荐机构胜率摘要。"""
        ...


class PaperPort(Protocol):
    def list_positions(self, account_id: str) -> list[dict]: ...

    def place_order(
        self, account_id: str, symbol: str, side: str, quantity: int, note: str = ""
    ) -> dict: ...


class WatchlistPort(Protocol):
    def list_symbols(self) -> list[str]:
        """自选股。第一版可用空列表或配置。"""
        ...
