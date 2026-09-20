"""papertrade 表读写。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from signal_papertrade.models import Account, NavPoint, Order, Position, utcnow


def create_account(
    session: Session,
    name: str,
    initial_cash: float = 1_000_000.0,
    **fee_kwargs,
) -> Account:
    if session.execute(select(Account).where(Account.name == name)).scalar_one_or_none():
        raise ValueError(f"账户已存在: {name}")
    acct = Account(name=name, cash=initial_cash, initial_cash=initial_cash, **fee_kwargs)
    session.add(acct)
    session.flush()
    return acct


def get_account(session: Session, account_id: str) -> Account | None:
    return session.get(Account, account_id)


def list_accounts(session: Session) -> Sequence[Account]:
    return session.execute(select(Account).order_by(Account.created_at)).scalars().all()


def place_order(
    session: Session,
    account_id: str,
    symbol: str,
    side: str,
    quantity: int,
    *,
    source: str = "manual",
    note: str = "",
) -> Order:
    if side not in ("buy", "sell"):
        raise ValueError("side 必须是 buy 或 sell")
    if quantity <= 0:
        raise ValueError("quantity 必须 > 0")
    acct = get_account(session, account_id)
    if not acct:
        raise KeyError(account_id)
    odd_lot = quantity % acct.lot_size != 0
    full_exit = False
    if side == "sell" and odd_lot:
        pos = get_position(session, account_id, symbol)
        full_exit = bool(pos and pos.quantity == quantity)
    if odd_lot and not full_exit:
        raise ValueError(f"数量必须是 {acct.lot_size} 的整数倍(清仓余股除外)")
    order = Order(
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        source=source,
        note=note,
        status="pending",
    )
    session.add(order)
    session.flush()
    return order


def list_orders(
    session: Session, account_id: str, status: str | None = None, limit: int = 100
) -> Sequence[Order]:
    q = (
        select(Order)
        .where(Order.account_id == account_id)
        .order_by(Order.submitted_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(Order.status == status)
    return session.execute(q).scalars().all()


def pending_orders(session: Session, account_id: str | None = None) -> Sequence[Order]:
    q = select(Order).where(Order.status == "pending").order_by(Order.submitted_at)
    if account_id:
        q = q.where(Order.account_id == account_id)
    return session.execute(q).scalars().all()


def get_position(session: Session, account_id: str, symbol: str) -> Position | None:
    return session.get(Position, {"account_id": account_id, "symbol": symbol})


def list_positions(session: Session, account_id: str) -> Sequence[Position]:
    return (
        session.execute(
            select(Position).where(Position.account_id == account_id, Position.quantity > 0)
        )
        .scalars()
        .all()
    )


def upsert_position(
    session: Session, account_id: str, symbol: str, quantity: int, avg_cost: float
) -> Position:
    pos = get_position(session, account_id, symbol)
    if pos is None:
        pos = Position(account_id=account_id, symbol=symbol, quantity=quantity, avg_cost=avg_cost)
        session.add(pos)
    else:
        pos.quantity = quantity
        pos.avg_cost = avg_cost
        pos.updated_at = utcnow()
    session.flush()
    return pos


def upsert_nav(
    session: Session,
    account_id: str,
    trade_date: date,
    cash: float,
    market_value: float,
    nav: float,
    bench_nav: float | None = None,
) -> NavPoint:
    point = session.get(NavPoint, {"account_id": account_id, "trade_date": trade_date})
    if point is None:
        point = NavPoint(
            account_id=account_id,
            trade_date=trade_date,
            cash=cash,
            market_value=market_value,
            nav=nav,
            bench_nav=bench_nav,
        )
        session.add(point)
    else:
        point.cash = cash
        point.market_value = market_value
        point.nav = nav
        point.bench_nav = bench_nav
    session.flush()
    return point


def list_nav(session: Session, account_id: str) -> Sequence[NavPoint]:
    return (
        session.execute(
            select(NavPoint).where(NavPoint.account_id == account_id).order_by(NavPoint.trade_date)
        )
        .scalars()
        .all()
    )
