"""AKShare 适配器(主数据源,免费)。

qfq_factor 由两次调用推导:adjust=""(原始)与 adjust="qfq"(前复权),
factor = qfq_close / raw_close。行情源被封 IP/变更接口时抛 ProviderError,由上层降级。
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from signal_datahub.providers.base import BAR_COLUMNS, ProviderError, validate_bars
from signal_datahub.symbols import bare_code, is_index_symbol, normalize_symbol

_COLUMN_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}


class AkshareProvider:
    name = "akshare"

    def __init__(self, request_interval_sec: float = 0.5) -> None:
        self._interval = request_interval_sec

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _hist(self, code6: str, start: date, end: date, adjust: str) -> pd.DataFrame:
        import akshare as ak

        time.sleep(self._interval)
        return ak.stock_zh_a_hist(
            symbol=code6,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def _index_hist(self, code6: str, start: date, end: date) -> pd.DataFrame:
        import akshare as ak

        time.sleep(self._interval)
        return ak.index_zh_a_hist(
            symbol=code6,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

    def fetch_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        code6 = bare_code(normalize_symbol(symbol))
        try:
            if is_index_symbol(symbol):
                raw = self._index_hist(code6, start, end)
                if raw is None or raw.empty:
                    return pd.DataFrame(columns=BAR_COLUMNS)
                # 指数无复权;qfq_factor 恒为 1
                return normalize_hist(raw, None)
            raw = self._hist(code6, start, end, adjust="")
            qfq = self._hist(code6, start, end, adjust="qfq")
        except Exception as e:  # akshare 内部异常类型不稳定,统一包装
            raise ProviderError(f"akshare 拉取 {symbol} 失败: {e}") from e
        if raw is None or raw.empty:
            return pd.DataFrame(columns=BAR_COLUMNS)
        return normalize_hist(raw, qfq)

    def fetch_instruments(self) -> pd.DataFrame:
        import akshare as ak

        try:
            df = ak.stock_info_a_code_name()
        except Exception as e:
            raise ProviderError(f"akshare 拉取股票列表失败: {e}") from e
        out = pd.DataFrame(
            {
                "symbol": df["code"].astype(str).map(normalize_symbol),
                "name": df["name"].astype(str),
            }
        )
        out["exchange"] = out["symbol"].str.split(".").str[1]
        return out

    def fetch_index_constituents(self, index_code: str) -> list[str]:
        import akshare as ak

        try:
            df = ak.index_stock_cons_csindex(symbol=index_code)
        except Exception as e:
            raise ProviderError(f"akshare 拉取指数 {index_code} 成分失败: {e}") from e
        return sorted(df["成分券代码"].astype(str).map(normalize_symbol))


def normalize_hist(raw: pd.DataFrame, qfq: pd.DataFrame | None) -> pd.DataFrame:
    """把 akshare 中文列 DataFrame 规范化为统一 bars 契约(纯函数,可单测)。"""
    df = raw.rename(columns=_COLUMN_MAP)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    if qfq is not None and not qfq.empty:
        q = qfq.rename(columns=_COLUMN_MAP).loc[:, ["trade_date", "close"]]
        q.columns = ["trade_date", "qfq_close"]
        q["trade_date"] = pd.Series(pd.to_datetime(q["trade_date"])).dt.date
        df = df.merge(q, on="trade_date", how="left")
        df["qfq_factor"] = (df["qfq_close"] / df["close"]).fillna(1.0)
        df = df.drop(columns=["qfq_close"])
    else:
        df["qfq_factor"] = 1.0
    return validate_bars(df, "akshare")
