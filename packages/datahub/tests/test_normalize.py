"""provider 规范化纯函数测试(fixture 数据,不依赖网络)。"""

import pandas as pd
import pytest
from signal_datahub.providers.akshare_provider import normalize_hist
from signal_datahub.providers.base import BAR_COLUMNS, ProviderError, validate_bars
from signal_datahub.providers.tushare_provider import normalize_daily


def make_ak_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-07-01", "2026-07-02"],
            "开盘": [10.0, 10.5],
            "最高": [11.0, 11.5],
            "最低": [9.8, 10.2],
            "收盘": [10.5, 11.0],
            "成交量": [1000, 1200],
            "成交额": [1.05e7, 1.32e7],
        }
    )


def make_ak_qfq() -> pd.DataFrame:
    df = make_ak_raw()
    df["收盘"] = [5.25, 5.5]  # 假设 qfq 是原始价一半
    return df


class TestAkshareNormalize:
    def test_columns_and_factor(self):
        out = normalize_hist(make_ak_raw(), make_ak_qfq())
        assert list(out.columns) == BAR_COLUMNS
        assert out["qfq_factor"].tolist() == pytest.approx([0.5, 0.5])
        assert out["close"].tolist() == [10.5, 11.0]  # 存原始价

    def test_no_qfq_defaults_to_one(self):
        out = normalize_hist(make_ak_raw(), None)
        assert out["qfq_factor"].tolist() == [1.0, 1.0]

    def test_sorted_by_date(self):
        raw = make_ak_raw().iloc[::-1]  # 倒序输入
        out = normalize_hist(raw, None)
        assert out["trade_date"].is_monotonic_increasing


class TestTushareNormalize:
    def make_daily(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": ["20260702", "20260701"],  # tushare 默认倒序
                "open": [10.5, 10.0],
                "high": [11.5, 11.0],
                "low": [10.2, 9.8],
                "close": [11.0, 10.5],
                "vol": [1200, 1000],
                "amount": [13200.0, 10500.0],  # 千元
            }
        )

    def test_normalize(self):
        adj = pd.DataFrame({"trade_date": ["20260701", "20260702"], "adj_factor": [1.0, 2.0]})
        out = normalize_daily(self.make_daily(), adj)
        assert list(out.columns) == BAR_COLUMNS
        assert out["amount"].tolist() == [10500000.0, 13200000.0]  # 千元→元
        assert out["qfq_factor"].tolist() == pytest.approx([0.5, 1.0])  # 锚定区间末日
        assert out["trade_date"].is_monotonic_increasing


def test_validate_bars_rejects_missing_columns():
    with pytest.raises(ProviderError):
        validate_bars(pd.DataFrame({"trade_date": []}), "x")


def test_validate_bars_rejects_duplicate_dates():
    df = pd.DataFrame([dict.fromkeys(BAR_COLUMNS, 1) for _ in range(2)])
    with pytest.raises(ProviderError):
        validate_bars(df, "x")
