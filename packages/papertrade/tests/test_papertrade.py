from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from signal_papertrade.engine import (
    apply_slippage,
    calc_commission,
    limit_band,
    performance_metrics,
    try_fill_with_limits,
)
from signal_papertrade.models import Account, Base
from signal_papertrade.service import PaperService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

CN = ZoneInfo("Asia/Shanghai")


class FakePrices:
    def __init__(self):
        # 7 个交易日,价格缓涨
        self.dates = [date(2026, 7, 1) + timedelta(days=i) for i in range(7)]
        self.data = {
            "600519.SH": {d: (100.0 + i, 100.5 + i) for i, d in enumerate(self.dates)},
            "000300.SH": {d: (1.0, 1.0 + i * 0.001) for i, d in enumerate(self.dates)},
        }

    def get_open_close(self, symbol, trade_date):
        return self.data.get(symbol, {}).get(trade_date)

    def get_prev_close(self, symbol, trade_date):
        prev = [d for d in self.dates if d < trade_date]
        if not prev:
            return None
        oc = self.get_open_close(symbol, prev[-1])
        return oc[1] if oc else None

    def list_trade_dates(self, start, end):
        return [d for d in self.dates if start <= d <= end]


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def svc():
    return PaperService(FakePrices())


def test_commission_and_slippage():
    assert calc_commission(1000, 0.00025, 5) == 5.0
    assert calc_commission(100_000, 0.00025, 5) == 25.0
    assert apply_slippage(100, "buy", 10) == 100.1
    assert apply_slippage(100, "sell", 10) == 99.9


def test_limit_band_chinext():
    _, hi = limit_band(100, "300750.SZ")
    assert abs(hi - 120) < 1e-9
    _, hi2 = limit_band(100, "600519.SH")
    assert abs(hi2 - 110) < 1e-9


def test_reject_limit_up_buy(session):
    acct = Account(
        name="t",
        cash=1_000_000,
        initial_cash=1_000_000,
        commission_rate=0,
        commission_min=0,
        stamp_tax_rate=0,
        slippage_bps=0,
    )
    # 昨收 100,今开 110 = 涨停
    r = try_fill_with_limits(
        account=acct,
        symbol="600519.SH",
        side="buy",
        quantity=100,
        open_price=110.0,
        prev_close=100.0,
        cash=1_000_000,
        position_qty=0,
    )
    assert not r.ok
    assert "涨停" in (r.reason or "")


def test_buy_sell_roundtrip(session, svc):
    acct = svc.create_account(session, "demo", 1_000_000)
    # 7/1 下单,7/2 开盘成交
    order = svc.place_order(
        session,
        acct.id,
        "600519.SH",
        "buy",
        100,
        note="test",
    )
    # 把 submitted_at 调到 7/1
    order.submitted_at = datetime(2026, 7, 1, 10, 0, tzinfo=CN)
    session.commit()

    r = svc.run_day(session, date(2026, 7, 2), acct.id)
    assert r["filled"] == 1
    session.refresh(acct)
    # open 7/2 = 101, slippage 5bps → 101 * 1.0005
    fill_px = 101 * 1.0005
    # commission max(amount*0.00025, 5)
    amount = fill_px * 100
    commission = max(amount * 0.00025, 5)
    expected_cash = 1_000_000 - amount - commission
    assert abs(float(acct.cash) - expected_cash) < 0.02

    from signal_papertrade import repo

    pos = repo.list_positions(session, acct.id)
    assert len(pos) == 1 and pos[0].quantity == 100

    navs = repo.list_nav(session, acct.id)
    assert len(navs) == 1
    assert float(navs[0].nav) > float(acct.cash)  # 含市值

    # 卖出
    sell = svc.place_order(session, acct.id, "600519.SH", "sell", 100)
    sell.submitted_at = datetime(2026, 7, 2, 10, 0, tzinfo=CN)
    session.commit()
    svc.run_day(session, date(2026, 7, 3), acct.id)
    session.refresh(acct)
    assert repo.list_positions(session, acct.id) == []
    # 价格上涨后卖出,现金可能高于初始(扣费后仍有盈利)
    assert float(acct.cash) > 990_000


def test_halted_position_uses_prev_close(session, svc):
    """停牌日无行情时,结算应沿用昨收,市值不归零。"""
    from signal_papertrade import repo

    acct = svc.create_account(session, "halt", 1_000_000)
    order = svc.place_order(session, acct.id, "600519.SH", "buy", 100)
    order.submitted_at = datetime(2026, 7, 1, 10, 0, tzinfo=CN)
    session.commit()
    svc.run_day(session, date(2026, 7, 2), acct.id)
    session.refresh(acct)

    # 伪造停牌:删掉 7/3 行情
    prices = svc._prices
    assert isinstance(prices, FakePrices)
    del prices.data["600519.SH"][date(2026, 7, 3)]
    svc.settle(session, date(2026, 7, 3), acct.id)
    nav = repo.list_nav(session, acct.id)[-1]
    assert nav.trade_date == date(2026, 7, 3)
    # 昨收 7/2 close = 101.5, 市值 = 100 * 101.5
    assert float(nav.market_value) == pytest.approx(100 * 101.5)
    assert float(nav.nav) == pytest.approx(float(acct.cash) + 100 * 101.5)


def test_reject_odd_lot_sell(session, svc):
    acct = svc.create_account(session, "lot", 1_000_000)
    with pytest.raises(ValueError, match="整数倍"):
        svc.place_order(session, acct.id, "600519.SH", "sell", 50)


def test_performance_metrics():
    m = performance_metrics([100, 110, 105, 120])
    assert m["total_return"] == pytest.approx(0.2)
    assert m["max_drawdown"] == pytest.approx(105 / 110 - 1)
