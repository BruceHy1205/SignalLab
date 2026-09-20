"""基准价锚定 + event study。

规则(architecture.md):
- 盘中推荐 → 当日收盘价(close_same_day)
- 收盘后推荐(≥15:00) → 次日开盘价(open_next_day)
- 停牌:顺延到下一根有成交的 K 线
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pandas as pd

WINDOWS = (1, 3, 5, 10, 20, 60)
MARKET_CLOSE = time(15, 0)


@dataclass(frozen=True)
class Baseline:
    date: date
    price: float
    rule: str


@dataclass(frozen=True)
class WindowPerf:
    window_days: int
    abs_return: float | None
    excess_return: float | None
    max_drawdown: float | None
    max_runup: float | None
    hit_target_first: bool | None
    hit_stop_first: bool | None
    as_of_date: date | None


def anchor_baseline(message_time: datetime, bars: pd.DataFrame) -> Baseline | None:
    """bars 列:trade_date, open, close;升序。返回 None 表示无法锚定。"""
    if bars.empty:
        return None
    msg_date = message_time.date()
    after_close = message_time.time() >= MARKET_CLOSE
    dates = list(bars["trade_date"])

    if after_close:
        # 次日及之后第一根
        candidates = [d for d in dates if d > msg_date]
        rule = "open_next_day"
        price_col = "open"
    else:
        # 当日或之后第一根(当日停牌则顺延)
        candidates = [d for d in dates if d >= msg_date]
        rule = "close_same_day"
        price_col = "close"

    if not candidates:
        return None
    d = candidates[0]
    row = bars.loc[bars["trade_date"] == d].iloc[0]
    return Baseline(date=d, price=float(row[price_col]), rule=rule)


def compute_windows(
    bars: pd.DataFrame,
    baseline: Baseline,
    benchmark_bars: pd.DataFrame | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
) -> list[WindowPerf]:
    """对每个窗口计算收益指标。bars/benchmark 均为前复权。"""
    stock = bars[bars["trade_date"] >= baseline.date].reset_index(drop=True)
    if stock.empty or float(stock.iloc[0]["close"]) == 0:
        return [WindowPerf(w, None, None, None, None, None, None, None) for w in WINDOWS]

    # 基准日收盘作为净值起点(即使锚定用的是 open,也用当日 close 做后续路径一致性)
    # 更精确:路径从 baseline 价起步
    base_px = baseline.price
    path = stock.copy()
    path["ret"] = path["close"].astype(float) / base_px - 1.0

    bench_ret = None
    if benchmark_bars is not None and not benchmark_bars.empty:
        b = benchmark_bars[benchmark_bars["trade_date"] >= baseline.date].reset_index(drop=True)
        if not b.empty:
            b0 = float(b.iloc[0]["close"])
            if b0:
                bench_map = {
                    d: float(c) / b0 - 1.0
                    for d, c in zip(b["trade_date"], b["close"], strict=False)
                }
                bench_ret = bench_map

    results: list[WindowPerf] = []
    for w in WINDOWS:
        # T+w:第 w 个交易日(baseline 当日为 T+0)
        if len(path) <= w:
            results.append(
                WindowPerf(
                    w,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    path.iloc[-1]["trade_date"] if len(path) else None,
                )
            )
            continue
        window = path.iloc[: w + 1]
        abs_r = float(window.iloc[-1]["ret"])
        as_of = window.iloc[-1]["trade_date"]
        excess = None
        if bench_ret is not None and as_of in bench_ret:
            excess = abs_r - bench_ret[as_of]
        rets = window["ret"].astype(float)
        max_runup = float(rets.max())
        # 期间最大回撤:相对窗口内峰值
        peak = rets.cummax()
        dd = float((rets - peak).min())
        hit_t, hit_s = _hit_flags(window, target_price, stop_loss)
        results.append(WindowPerf(w, abs_r, excess, dd, max_runup, hit_t, hit_s, as_of))
    return results


def _hit_flags(
    window: pd.DataFrame, target: float | None, stop: float | None
) -> tuple[bool | None, bool | None]:
    if target is None and stop is None:
        return None, None
    first: str | None = None
    for high, low in zip(
        window["high"].astype(float).tolist(),
        window["low"].astype(float).tolist(),
        strict=True,
    ):
        if first is None and target is not None and high >= target:
            first = "target"
        if first is None and stop is not None and low <= stop:
            first = "stop"
    return (
        (first == "target") if target is not None else None,
        (first == "stop") if stop is not None else None,
    )


def trading_days_ahead(from_date: date, n: int) -> date:
    """粗略日历估算(用于拉行情区间),真正窗口按交易日切片。"""
    return from_date + timedelta(days=int(n * 1.7) + 5)
