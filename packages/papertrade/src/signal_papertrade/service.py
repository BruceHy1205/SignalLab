"""模拟盘服务:下单、撮合、结算。"""

from __future__ import annotations

import logging
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from signal_papertrade import repo
from signal_papertrade.engine import (
    new_avg_cost,
    performance_metrics,
    try_fill_with_limits,
)
from signal_papertrade.ports import PriceReader

logger = logging.getLogger(__name__)
CN = ZoneInfo("Asia/Shanghai")
BENCHMARK = "000300.SH"


class PaperService:
    def __init__(self, prices: PriceReader) -> None:
        self._prices = prices

    def create_account(self, session: Session, name: str, initial_cash: float = 1_000_000.0):
        acct = repo.create_account(session, name, initial_cash)
        # 初始净值点:用今天或最近交易日
        session.commit()
        return acct

    def place_order(
        self,
        session: Session,
        account_id: str,
        symbol: str,
        side: str,
        quantity: int,
        *,
        source: str = "manual",
        note: str = "",
    ):
        order = repo.place_order(
            session, account_id, symbol, side, quantity, source=source, note=note
        )
        session.commit()
        return order

    def match_pending(
        self, session: Session, trade_date: date, account_id: str | None = None
    ) -> dict:
        """把 pending 订单按 trade_date 开盘价撮合。

        规则:仅成交 submitted_at 日期 < trade_date 的订单(次日开盘)。
        """
        orders = repo.pending_orders(session, account_id)
        filled = rejected = skipped = 0
        for order in orders:
            submitted_day = order.submitted_at.astimezone(CN).date()
            if submitted_day >= trade_date:
                skipped += 1
                continue
            acct = repo.get_account(session, order.account_id)
            if not acct:
                continue
            oc = self._prices.get_open_close(order.symbol, trade_date)
            if oc is None:
                order.status = "rejected"
                order.reject_reason = "无行情"
                rejected += 1
                continue
            open_px, _ = oc
            prev = self._prices.get_prev_close(order.symbol, trade_date)
            pos = repo.get_position(session, order.account_id, order.symbol)
            pos_qty = pos.quantity if pos else 0
            cash = float(acct.cash)
            result = try_fill_with_limits(
                account=acct,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                open_price=open_px,
                prev_close=prev,
                cash=cash,
                position_qty=pos_qty,
            )
            if not result.ok:
                order.status = "rejected"
                order.reject_reason = result.reason
                rejected += 1
                continue

            assert result.price is not None and result.amount is not None
            assert result.commission is not None
            if order.side == "buy":
                acct.cash = cash - result.amount - result.commission
                new_qty = pos_qty + order.quantity
                avg = new_avg_cost(
                    pos_qty,
                    pos.avg_cost if pos else 0.0,
                    order.quantity,
                    result.price,
                    result.commission,
                )
                repo.upsert_position(session, order.account_id, order.symbol, new_qty, avg)
            else:
                # commission 字段已含印花税
                acct.cash = cash + result.amount - result.commission
                new_qty = pos_qty - order.quantity
                avg = pos.avg_cost if pos and new_qty > 0 else 0.0
                repo.upsert_position(session, order.account_id, order.symbol, new_qty, avg)

            order.status = "filled"
            order.fill_date = trade_date
            order.fill_price = result.price
            order.fill_amount = result.amount
            order.commission = result.commission
            filled += 1
        session.commit()
        return {"filled": filled, "rejected": rejected, "skipped": skipped}

    def settle(self, session: Session, trade_date: date, account_id: str | None = None) -> dict:
        """收盘结算:市值盯市 + 写 nav。可先 match 再 settle。"""
        accounts = (
            [repo.get_account(session, account_id)]
            if account_id
            else list(repo.list_accounts(session))
        )
        n = 0
        for acct in accounts:
            if not acct:
                continue
            mv = 0.0
            for pos in repo.list_positions(session, acct.id):
                oc = self._prices.get_open_close(pos.symbol, trade_date)
                if oc is not None:
                    close_px = oc[1]
                else:
                    # 停牌:用最近收盘价盯市,避免市值瞬间归零
                    prev = self._prices.get_prev_close(pos.symbol, trade_date)
                    if prev is None:
                        continue
                    close_px = prev
                mv += pos.quantity * close_px
            cash = float(acct.cash)
            nav = cash + mv
            # 基准归一化:以账户初始净值为 1,同步乘以指数涨跌
            bench_nav = None
            oc_b = self._prices.get_open_close(BENCHMARK, trade_date)
            if oc_b:
                bench_nav = oc_b[1]  # 存绝对收盘,前端归一
            elif (prev_b := self._prices.get_prev_close(BENCHMARK, trade_date)) is not None:
                bench_nav = prev_b
            repo.upsert_nav(session, acct.id, trade_date, cash, mv, nav, bench_nav)
            n += 1
        session.commit()
        return {"settled": n}

    def run_day(self, session: Session, trade_date: date, account_id: str | None = None) -> dict:
        """完整一日:撮合 + 结算。"""
        m = self.match_pending(session, trade_date, account_id)
        s = self.settle(session, trade_date, account_id)
        return {**m, **s}

    def account_performance(self, session: Session, account_id: str) -> dict:
        points = repo.list_nav(session, account_id)
        if not points:
            return performance_metrics([])
        navs = [float(p.nav) for p in points]
        benches = [float(p.bench_nav) for p in points if p.bench_nav is not None]
        if len(benches) != len(navs):
            benches = None
        else:
            # 归一化基准到与初始 nav 同起点
            b0 = benches[0]
            n0 = navs[0]
            benches = [n0 * (b / b0) for b in benches] if b0 else None
        return performance_metrics(navs, benches)

    def auto_run_through(self, session: Session, account_id: str, start: date, end: date) -> dict:
        """从 start 到 end 逐个交易日撮合结算(回放/补跑)。"""
        dates = self._prices.list_trade_dates(start, end)
        summary = {"days": 0, "filled": 0, "rejected": 0}
        for d in dates:
            r = self.run_day(session, d, account_id)
            summary["days"] += 1
            summary["filled"] += r.get("filled", 0)
            summary["rejected"] += r.get("rejected", 0)
        return summary
