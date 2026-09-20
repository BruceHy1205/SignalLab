from datetime import date
from uuid import uuid4

import pandas as pd
from signal_research.validator import (
    build_stub_package_zip,
    generate_signals_for_date,
    independent_verify,
    load_package,
)


def test_load_and_verify_stub_zip():
    data = build_stub_package_zip(package_id=str(uuid4()), ic=0.03)
    contents = load_package(data)
    assert contents.manifest.factors[0].expression
    result = independent_verify(contents, {})
    assert result.ok
    assert result.verified_metrics.get("verify_skipped") is True


def test_verify_with_bars_same_sign():
    # stub 因子 Ref(close,1)/close-1 在单边上行序列上 IC 为负
    data = build_stub_package_zip(package_id=str(uuid4()), ic=-0.02)
    contents = load_package(data)
    n = 40
    dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=n)]
    bars = {
        "600519.SH": pd.DataFrame(
            {
                "trade_date": dates,
                "open": [100] * n,
                "high": [101] * n,
                "low": [99] * n,
                "close": [100 + i * 0.5 for i in range(n)],
                "volume": [1e6] * n,
            }
        )
    }
    result = independent_verify(contents, bars)
    assert result.ok
    assert "sample_ic" in result.verified_metrics


def test_generate_signals():
    data = build_stub_package_zip(package_id=str(uuid4()))
    contents = load_package(data)
    n = 30
    dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=n)]
    bars = {}
    for i, sym in enumerate(["600519.SH", "000001.SZ", "300750.SZ"]):
        bars[sym] = pd.DataFrame(
            {
                "trade_date": dates,
                "open": [10] * n,
                "high": [11] * n,
                "low": [9] * n,
                "close": [10 + i + j * 0.1 for j in range(n)],
                "volume": [1e6] * n,
            }
        )
    rows = generate_signals_for_date(contents, bars, date(2024, 2, 15), top_n=1)
    assert rows
    assert rows[0]["action"] in ("buy", "sell")
