import pandas as pd
import pytest
from signal_research.expr import ExprError, eval_expression


def _bars(n: int = 20) -> pd.DataFrame:
    dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=n)]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": [10.0] * n,
            "high": [11.0] * n,
            "low": [9.0] * n,
            "close": [10.0 + i * 0.1 for i in range(n)],
            "volume": [1e6] * n,
        }
    )


def test_ref_close():
    out = eval_expression("Ref($close, 1) / $close - 1", _bars())
    assert len(out) == 20
    assert pd.isna(out.iloc[0])
    assert out.iloc[1] == pytest.approx(10.0 / 10.1 - 1)


def test_mean():
    out = eval_expression("Mean($close, 3)", _bars(5))
    assert out.iloc[2] == pytest.approx((10.0 + 10.1 + 10.2) / 3)


def test_rejects_unknown():
    with pytest.raises(ExprError):
        eval_expression("$foo", _bars())
