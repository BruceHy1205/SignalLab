"""撮合与结算引擎(纯逻辑,可单测)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from signal_papertrade.models import Account


@dataclass(frozen=True)
class FillResult:
    ok: bool
    price: float | None = None
    amount: float | None = None
    commission: float | None = None
    reason: str | None = None


def apply_slippage(price: float, side: str, slippage_bps: float) -> float:
    """买入上浮、卖出下浮。"""
    adj = price * (slippage_bps / 10_000.0)
    return price + adj if side == "buy" else price - adj


def calc_commission(amount: float, rate: float, minimum: float) -> float:
    return max(amount * rate, minimum)


def limit_band(prev_close: float, symbol: str) -> tuple[float, float]:
    """粗略涨跌停:创业板/科创板 ±20%,其余 ±10%。"""
    code = symbol.split(".")[0]
    pct = 0.20 if code.startswith(("3", "68")) else 0.10
    return prev_close * (1 - pct), prev_close * (1 + pct)


def try_fill(
    *,
    account: Account,
    side: str,
    quantity: int,
    open_price: float,
    cash: float,
    position_qty: int,
) -> FillResult:
    """尝试按开盘价成交一笔,返回结果(不改账户,由调用方落库)。"""
    if open_price <= 0:
        return FillResult(False, reason="无效开盘价")

    px = apply_slippage(open_price, side, account.slippage_bps)
    amount = px * quantity

    if side == "buy":
        commission = calc_commission(amount, account.commission_rate, account.commission_min)
        total = amount + commission
        if total > cash + 1e-6:
            return FillResult(False, reason="现金不足")
        return FillResult(True, price=px, amount=amount, commission=commission)

    if quantity > position_qty:
        return FillResult(False, reason="持仓不足")
    commission = calc_commission(amount, account.commission_rate, account.commission_min)
    stamp = amount * account.stamp_tax_rate
    return FillResult(True, price=px, amount=amount, commission=commission + stamp)


def try_fill_with_limits(
    *,
    account: Account,
    symbol: str,
    side: str,
    quantity: int,
    open_price: float,
    prev_close: float | None,
    cash: float,
    position_qty: int,
) -> FillResult:
    if prev_close and prev_close > 0:
        lo, hi = limit_band(prev_close, symbol)
        if side == "buy" and open_price >= hi * 0.999:
            return FillResult(False, reason="涨停无法买入")
        if side == "sell" and open_price <= lo * 1.001:
            return FillResult(False, reason="跌停无法卖出")
    return try_fill(
        account=account,
        side=side,
        quantity=quantity,
        open_price=open_price,
        cash=cash,
        position_qty=position_qty,
    )


def new_avg_cost(
    old_qty: int, old_cost: float, buy_qty: int, buy_price: float, commission: float
) -> float:
    """买入后摊薄成本(含佣金)。"""
    total_cost = old_qty * old_cost + buy_qty * buy_price + commission
    new_qty = old_qty + buy_qty
    return total_cost / new_qty if new_qty else 0.0


def performance_metrics(
    nav_series: list[float],
    bench_series: list[float] | None = None,
    trading_days_per_year: int = 242,
) -> dict:
    """累计收益、年化、最大回撤、相对基准超额。"""
    if len(nav_series) < 2 or nav_series[0] == 0:
        return {
            "total_return": None,
            "annualized": None,
            "max_drawdown": None,
            "excess_return": None,
        }
    total = nav_series[-1] / nav_series[0] - 1.0
    n = len(nav_series) - 1
    annualized = (1 + total) ** (trading_days_per_year / n) - 1 if n > 0 else None
    peak = nav_series[0]
    max_dd = 0.0
    for v in nav_series:
        peak = max(peak, v)
        dd = v / peak - 1.0
        max_dd = min(max_dd, dd)
    excess = None
    if bench_series and len(bench_series) == len(nav_series) and bench_series[0]:
        bench_total = bench_series[-1] / bench_series[0] - 1.0
        excess = total - bench_total
    return {
        "total_return": total,
        "annualized": annualized,
        "max_drawdown": max_dd,
        "excess_return": excess,
    }


def next_trading_day(dates: list[date], after: date) -> date | None:
    for d in dates:
        if d > after:
            return d
    return None
