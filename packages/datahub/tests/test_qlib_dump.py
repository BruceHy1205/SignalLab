"""qlib dump_bin 导出与 bin 往返对账。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from signal_datahub.models import Base
from signal_datahub.qlib_dump import dump_qlib_snapshot, read_feature_bin
from signal_datahub.repo import upsert_daily_bars, upsert_instruments
from signal_datahub.symbols import from_qlib_code, to_qlib_code
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed(session: Session) -> None:
    upsert_instruments(
        session,
        pd.DataFrame(
            [
                {"symbol": "600519.SH", "name": "贵州茅台", "exchange": "SH"},
                {"symbol": "000001.SZ", "name": "平安银行", "exchange": "SZ"},
            ]
        ),
    )
    for symbol, base in (("600519.SH", 100.0), ("000001.SZ", 10.0)):
        rows = []
        for i, d in enumerate(
            [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
        ):
            # 000001 缺 1/4,测缺日对齐
            if symbol == "000001.SZ" and d == date(2024, 1, 4):
                continue
            px = base + i
            rows.append(
                {
                    "trade_date": d,
                    "open": px,
                    "high": px + 1,
                    "low": px - 1,
                    "close": px,
                    "volume": 1000 + i,
                    "amount": 1e6,
                    "qfq_factor": 0.5,
                }
            )
        upsert_daily_bars(session, symbol, pd.DataFrame(rows), source="test")
    session.commit()


def test_symbol_qlib_roundtrip():
    assert to_qlib_code("600519.SH") == "sh600519"
    assert from_qlib_code("sh600519") == "600519.SH"
    assert from_qlib_code("sz000001") == "000001.SZ"


def test_dump_qlib_snapshot(tmp_path):
    with _session() as session:
        _seed(session)
        result = dump_qlib_snapshot(
            session,
            tmp_path,
            snapshot_name="qlib_cn_test",
            universe_symbols=["600519.SH"],
        )
        assert result.n_symbols == 2
        assert result.n_calendar_days == 4
        root = result.out_dir
        assert (root / "calendars" / "day.txt").exists()
        assert (root / "instruments" / "all.txt").exists()
        assert (root / "instruments" / "csi300.txt").exists()
        assert (root / "meta.json").exists()

        cal = (root / "calendars" / "day.txt").read_text(encoding="utf-8").strip().splitlines()
        assert cal[0] == "2024-01-02"
        assert cal[-1] == "2024-01-05"

        # 茅台:因子 0.5 → close qfq = raw*0.5
        start, closes = read_feature_bin(root / "features" / "sh600519" / "close.day.bin")
        assert start == 0
        assert len(closes) == 4
        np.testing.assert_allclose(closes[0], 100.0 * 0.5, rtol=1e-5)
        np.testing.assert_allclose(closes[3], 103.0 * 0.5, rtol=1e-5)

        # 平安:缺 1/4 → 对应位置为 nan
        start2, closes2 = read_feature_bin(root / "features" / "sz000001" / "close.day.bin")
        assert start2 == 0
        assert len(closes2) == 4  # 1/2..1/5
        assert np.isnan(closes2[2])  # 1/4
        np.testing.assert_allclose(closes2[0], 10.0 * 0.5, rtol=1e-5)
        np.testing.assert_allclose(closes2[3], 13.0 * 0.5, rtol=1e-5)

        csi = (root / "instruments" / "csi300.txt").read_text(encoding="utf-8")
        assert "sh600519" in csi
        assert "sz000001" not in csi
