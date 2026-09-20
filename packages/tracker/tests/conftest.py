from datetime import date

import pandas as pd
import pytest
from signal_tracker.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class FakeBars:
    """内存行情:茅台 + 沪深300。"""

    def __init__(self):
        dates = [d.date() for d in pd.bdate_range("2026-07-01", periods=30)]
        self.stock = pd.DataFrame(
            {
                "trade_date": dates,
                "open": [100 + i for i in range(30)],
                "high": [101 + i for i in range(30)],
                "low": [99 + i for i in range(30)],
                "close": [100.5 + i for i in range(30)],
            }
        )
        self.bench = pd.DataFrame(
            {
                "trade_date": dates,
                "open": [1] * 30,
                "high": [1] * 30,
                "low": [1] * 30,
                "close": [1.0 + i * 0.001 for i in range(30)],
            }
        )

    def get_qfq_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        df = self.bench if symbol.startswith("000300") else self.stock
        out = df.loc[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        return pd.DataFrame(out).reset_index(drop=True)

    def resolve_symbol(self, name: str):
        if "茅台" in name:
            return [("600519.SH", "贵州茅台")]
        return []

    def list_aliases(self) -> dict[str, str]:
        return {"贵州茅台": "600519.SH", "茅台": "600519.SH"}


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def fake_bars():
    return FakeBars()
