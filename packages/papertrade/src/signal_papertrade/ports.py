"""PriceReader:papertrade 读行情的唯一接口(组装层注入)。"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class PriceReader(Protocol):
    def get_open_close(self, symbol: str, trade_date: date) -> tuple[float, float] | None:
        """返回 (open, close) 原始价;无数据返回 None。"""
        ...

    def get_prev_close(self, symbol: str, trade_date: date) -> float | None:
        """trade_date 前一交易日收盘价(涨跌停判断用)。"""
        ...

    def list_trade_dates(self, start: date, end: date) -> list[date]:
        """区间内交易日列表(升序)。可用任意活跃股票的交易日近似。"""
        ...
