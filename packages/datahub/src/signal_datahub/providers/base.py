"""BarProvider 接口:所有行情源实现同一契约,返回统一列名的 DataFrame。

统一 bars 列:trade_date(date), open, high, low, close, volume, amount, qfq_factor
统一 instruments 列:symbol, name, exchange
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

BAR_COLUMNS = ["trade_date", "open", "high", "low", "close", "volume", "amount", "qfq_factor"]


class ProviderError(RuntimeError):
    """行情源调用失败(重试耗尽后抛出),同步服务据此切换备用源。"""


class BarProvider(Protocol):
    name: str

    def fetch_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """返回 BAR_COLUMNS 列的 DataFrame,按 trade_date 升序。"""
        ...

    def fetch_instruments(self) -> pd.DataFrame:
        """返回全市场 A 股列表:symbol, name, exchange。"""
        ...

    def fetch_index_constituents(self, index_code: str) -> list[str]:
        """返回指数成分股 symbol 列表。index_code 如 '000300'。"""
        ...


def validate_bars(df: pd.DataFrame, provider: str) -> pd.DataFrame:
    """契约校验:列齐全、无重复交易日、按日期升序。"""
    missing = set(BAR_COLUMNS) - set(df.columns)
    if missing:
        raise ProviderError(f"{provider} 返回缺列: {missing}")
    df = df.loc[:, BAR_COLUMNS].sort_values(by="trade_date").reset_index(drop=True)
    if df["trade_date"].duplicated().any():
        raise ProviderError(f"{provider} 返回重复交易日")
    return df
