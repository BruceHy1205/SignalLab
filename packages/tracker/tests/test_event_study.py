from datetime import datetime
from zoneinfo import ZoneInfo

from signal_tracker.event_study import anchor_baseline, compute_windows

CN = ZoneInfo("Asia/Shanghai")


def test_anchor_same_day_close(fake_bars):
    bars = fake_bars.stock
    bl = anchor_baseline(datetime(2026, 7, 1, 10, 0, tzinfo=CN), bars)
    assert bl is not None
    assert bl.rule == "close_same_day"
    assert bl.date.isoformat() == "2026-07-01"
    assert bl.price == bars.iloc[0]["close"]


def test_anchor_after_close_next_open(fake_bars):
    bars = fake_bars.stock
    bl = anchor_baseline(datetime(2026, 7, 1, 15, 30, tzinfo=CN), bars)
    assert bl is not None
    assert bl.rule == "open_next_day"
    assert bl.date.isoformat() == "2026-07-02"
    assert bl.price == float(bars.iloc[1]["open"])


def test_compute_windows_abs_and_excess(fake_bars):
    bl = anchor_baseline(datetime(2026, 7, 1, 10, 0, tzinfo=CN), fake_bars.stock)
    assert bl is not None
    perfs = compute_windows(fake_bars.stock, bl, fake_bars.bench)
    p5 = next(p for p in perfs if p.window_days == 5)
    assert p5.abs_return is not None
    expected = float(fake_bars.stock.iloc[5]["close"]) / bl.price - 1
    assert abs(p5.abs_return - expected) < 1e-9
    assert p5.excess_return is not None
