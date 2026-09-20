"""Tushare 适配器(备用数据源,需 token,基础日线免费)。

qfq_factor 用 adj_factor 接口换算:qfq_factor = adj_factor / latest_adj_factor,
与 AKShare 的 qfq 口径一致(以区间末日为锚)。
"""

from __future__ import annotations

from datetime import date
from functools import cached_property

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from signal_datahub.providers.base import BAR_COLUMNS, ProviderError, validate_bars
from signal_datahub.symbols import is_index_symbol, normalize_symbol


def _ts_code(symbol: str) -> str:
    return normalize_symbol(symbol)  # tushare 格式恰好一致:600519.SH


class TushareProvider:
    name = "tushare"

    def __init__(self, token: str) -> None:
        self._token = token

    @cached_property
    def _pro(self):
        import tushare as ts

        ts.set_token(self._token)
        return ts.pro_api()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._pro.daily(
            ts_code=_ts_code(symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _index_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._pro.index_daily(
            ts_code=_ts_code(symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _adj_factor(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        return self._pro.adj_factor(
            ts_code=_ts_code(symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

    def fetch_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        try:
            if is_index_symbol(symbol):
                daily = self._index_daily(symbol, start, end)
                if daily is None or daily.empty:
                    return pd.DataFrame(columns=BAR_COLUMNS)
                return normalize_daily(daily, None)
            daily = self._daily(symbol, start, end)
            adj = self._adj_factor(symbol, start, end)
        except Exception as e:
            raise ProviderError(f"tushare 拉取 {symbol} 失败: {e}") from e
        if daily is None or daily.empty:
            return pd.DataFrame(columns=BAR_COLUMNS)
        return normalize_daily(daily, adj)

    def fetch_instruments(self) -> pd.DataFrame:
        try:
            df = self._pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        except Exception as e:
            raise ProviderError(f"tushare 拉取股票列表失败: {e}") from e
        out = pd.DataFrame(
            {"symbol": df["ts_code"].map(normalize_symbol), "name": df["name"].astype(str)}
        )
        out["exchange"] = out["symbol"].str.split(".").str[1]
        return out

    def fetch_index_constituents(self, index_code: str) -> list[str]:
        try:
            df = self._pro.index_weight(index_code=f"{index_code}.SH")
            latest = df[df["trade_date"] == df["trade_date"].max()]
        except Exception as e:
            raise ProviderError(f"tushare 拉取指数 {index_code} 成分失败: {e}") from e
        return sorted({normalize_symbol(c) for c in latest["con_code"]})


def normalize_daily(daily: pd.DataFrame, adj: pd.DataFrame | None) -> pd.DataFrame:
    """把 tushare daily + adj_factor 规范化为统一 bars 契约(纯函数,可单测)。

    tushare 单位换算:vol 为手(与统一契约一致),amount 为千元 → 元。
    """
    df = daily.rename(columns={"trade_date": "trade_date", "vol": "volume"})
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["amount"] = df["amount"].astype(float) * 1000.0
    if adj is not None and not adj.empty:
        a = adj.copy()
        a["trade_date"] = pd.to_datetime(a["trade_date"]).dt.date
        latest = a.sort_values("trade_date")["adj_factor"].iloc[-1]
        a["qfq_factor"] = a["adj_factor"] / latest
        df = df.merge(a[["trade_date", "qfq_factor"]], on="trade_date", how="left")
        df["qfq_factor"] = df["qfq_factor"].fillna(1.0)
    else:
        df["qfq_factor"] = 1.0
    return validate_bars(df, "tushare")
